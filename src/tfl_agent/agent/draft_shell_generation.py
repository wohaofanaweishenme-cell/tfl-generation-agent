"""Evidence-grounded *draft* Shell Spec v3.0 adapter and editable DOCX generator.

Read-only approved generic library; no additional model calls or source shells.
Candidate claims are not independently validated clinical requirements.
The adapter preserves this distinction in the spec, audit and visible Word text.
"""
from __future__ import annotations
import copy
import re
import subprocess
import sys
from pathlib import Path
from collections import Counter
from tfl_agent.agent.unified_pipeline import write_json, read_json, sha_file

VERSION = "draft-shell-v1"
UNKNOWN_KIND = "draft_unknown"
FAMILIES = {
    "TBL_VARIABLE_SUMMARY", "TBL_CRITERION_COUNTS", "TBL_CODED_TERM_HIERARCHY",
    "TBL_PARAMETER_BY_VISIT", "TBL_RESPONSE_RATE", "TBL_TIME_TO_EVENT",
    "TBL_CONTINUOUS_COMPARISON", "TBL_SHIFT_CROSSTAB",
    "TBL_TIMEPOINT_STATISTICS_COLUMNS",
}

def norm(text):
    return " ".join(re.findall(r"[a-z0-9]+", str(text).casefold()))

def tidy(text):
    return " ".join(str(text).split())

def unique(xs):
    return list(dict.fromkeys(xs))

def candidate_claims(result):
    """Recheck literal support. Never promote review-only or rejected claims."""
    chunks = {c["chunk_id"]: c for c in result["source_chunks"]}
    out = []
    for c in result["claim_audit"]:
        if c.get("rule_route") != "unverified_candidate" or not c.get("exact_match") or not c.get("literal_support"):
            continue
        v, q = c.get("value"), c.get("exact_quote")
        if not isinstance(v, str) or not v.strip() or not isinstance(q, str) or v not in q:
            continue
        if c.get("source") == "title":
            if q not in result["target"]["title"]:
                continue
        elif c.get("source") == "sap":
            if q not in chunks.get(c.get("chunk_id"), {}).get("text", "") or not c.get("source_spans"):
                continue
        else:
            continue
        out.append(c)
    return out

def choose_layout_preset(library, tid, result):
    """An owned proposed preset, a unique title alias hit, or sole family preset.
    Never present this layout choice as a confirmed study-specific preset.
    """
    owned = library.templates[tid]["presets"]
    proposal = result.get("proposed_preset")
    if proposal and any(p["preset_id"] == proposal for p in owned):
        return proposal, "agent_proposed_unconfirmed"
    if len(owned) == 1:
        return owned[0]["preset_id"], "sole_family_layout_unconfirmed"
    title = " " + norm(result["target"]["title"]) + " "
    hits = []
    for p in owned:
        terms = [p["name"], *p.get("aliases", []), *p.get("keywords", [])]
        if any(len(norm(t)) >= 6 and (" " + norm(t) + " ") in title for t in terms):
            hits.append(p["preset_id"])
    if len(hits) == 1:
        return hits[0], "unique_title_layout_cue_unconfirmed"
    return None, "no_unique_preset"

def statistic_kind(text, style):
    """Map only explicit statistic labels, not a vague mention of a method."""
    key = norm(text)
    aliases = {
        "number": "n", "count": "n", "counts": "n",
        "number and percentage": "n_pct", "number and percent": "n_pct",
        "n percent": "n_pct", "n percentage": "n_pct", "n pct": "n_pct",
        "percentage": "pct", "percent": "pct",
        "standard deviation": "sd", "mean and standard deviation": "mean_sd",
        "mean sd": "mean_sd", "standard error": "se",
        "minimum and maximum": "min_max", "min max": "min_max",
        "first and third quartiles": "q1_q3", "q1 q3": "q1_q3",
        "number of events": "events", "p value": "p_value",
    }
    if tidy(text) == "%":
        return "pct"
    for k,v in style["statistic_formats"].items():
        if key and key == norm(v["label"]):
            return k
    return aliases.get(key)

def build_draft_spec(result, library):
    """Bind only available candidate information. All uncertainty stays visible."""
    if not result.get("complete_candidate_pipeline"):
        raise ValueError("A complete candidate pipeline is required to render a draft")
    tid = result.get("recommended_template")
    if tid not in FAMILIES or tid not in library.templates:
        raise ValueError("No supported candidate table template")
    if result.get("generation_authorized") or result.get("confirmed_template"):
        raise ValueError("Expected unconfirmed candidate pipeline")
    template = library.template(tid)
    pid, preset_basis = choose_layout_preset(library, tid, result)
    preset = library.preset(tid,pid)["defaults"] if pid else {}
    title = result["target"]["title"]
    output_id = str(result["entry_id"])
    if not re.fullmatch(r"\d+(?:\.\d+)*", output_id):
        raise ValueError("A numeric TFL ID is required")
    claims = candidate_claims(result)
    issues, bindings = [], []
    style = copy.deepcopy(library.style)
    # Local draft-only placeholder, not an approved library statistic.
    style["statistic_formats"][UNKNOWN_KIND] = {"label": "[REVIEW: statistic]", "placeholder": "[TBD]"}

    def select(field, limit=180):
        return [c for c in claims if c["field"] == field and len(tidy(c["value"])) <= limit]
    def vals(cs):
        return unique(tidy(c["value"]) for c in cs)
    def issue(path, question, kind="missing"):
        qid = f"Q{len(issues)+1:03d}"
        if len(issues) >= 999:
            raise ValueError("Too many draft issues")
        issues.append({"question_id":qid,"element_path":path,"kind":kind,
                       "question":question,"answer":None})
        return qid
    def unresolved(path, hint, value=None):
        qid = issue(path,hint)
        return {"value":value,"source":"unresolved","status":"unresolved",
                "question_id":qid,"note":hint}
    def proposal(path,value,note="Provisional library layout, not a study requirement."):
        issue(path,note,"needs_review")
        return {"value":value,"source":"template_default","status":"needs_review","note":note}
    def approved(value):
        return {"value":value,"source":"template_default","status":"resolved"}
    def bound(path, value, cs):
        assert cs
        bindings.append({"element_path":path,"value":value,"status":"candidate_needs_review",
                         "claim_indices":unique(c["claim_index"] for c in cs),
                         "evidence":[{k:c.get(k) for k in ("claim_index","field","value","source","chunk_id","exact_quote","source_spans")} for c in cs]})
        return {"value":value,"source":"study_setting" if any(c["source"]=="sap" for c in cs) else "content_list",
                "status":"needs_review","note":"Unconfirmed candidate mapped from retained Agent claim(s); see Adaptation_Audit.json."}

    # A literal analysis-set suffix in the caller-provided target is title evidence only.
    suffix = re.search(r"(?:[–—-]\s*|\()([^()–—]+?(?:Analysis Set|Analysis Population|Population|All Patients|All Subjects))\)?\s*$",title,re.I)
    pop = select("analysis_population")
    if suffix:
        population={"value":suffix.group(1).strip(),"source":"content_list","status":"needs_review",
                    "note":"Explicit target-title suffix; not an independent SAP confirmation."}
        bindings.append({"element_path":"population","value":population["value"],"status":"title_candidate_needs_review","evidence":[{"source":"title","exact_quote":suffix.group(1)}]})
    elif len(vals(pop)) == 1:
        population=bound("population",vals(pop)[0],pop)
    else:
        population=unresolved("population","Confirm target analysis population")

    # Do not turn a generic grouping rule or a long arm definition into an arm label.
    generic_groups={"treatment","treatment group","treatment groups","group","groups","cohort","cohorts",
                    "each group","each treatment group","by treatment group","overall","total","all subjects","all patients"}
    group_claims=[c for c in select("treatment_groups",65)
                  if c["source"]=="sap" and norm(c["value"]) not in generic_groups
                  and len(tidy(c["value"]).split())<=8 and not re.search(r"[,;:=]|\b(?:and|or|will|were|are|by|each|subjects|patients)\b",c["value"],re.I)]
    group_names=vals(group_claims)
    groups=[]
    if 0<len(group_names)<=8:
        for i,g in enumerate(group_names,1):
            groups.append({"id":f"G{i}","label":bound(f"columns.groups[{i-1}].label",g,
                          [c for c in group_claims if tidy(c["value"])==g]),"show_n":True})
        # Group names are candidates; completeness and actual display are unknown.
        issue("columns.groups","Confirm complete set of group columns and labels.","needs_review")
    else:
        groups=[{"id":"G1","label":unresolved("columns.groups","Treatment group(s) / cohort(s)"),"show_n":True}]
    total_claims=[c for c in select("column_requirements",90) if c["source"]=="sap"]
    yes=[c for c in total_claims if norm(c["value"]) in {"total column","overall column","all subjects column","all patients column"}]
    no=[c for c in total_claims if norm(c["value"]) in {"no total column","without total column","no overall column"}]
    total=bound("columns.total.enabled",True,yes) if yes and not no else bound("columns.total.enabled",False,no) if no and not yes else unresolved("columns.total.enabled","Total column on/off and membership")
    stub=template.get("skeleton",{}).get("columns",{}).get("stub_header","Characteristic / statistic")
    columns={"stub_header":approved(stub),"groups":groups,
             "total":{"enabled":total,"label":approved("Total")}}
    stats=select("statistics",100)
    row_claims=select("row_requirements",100)
    endpoints=select("endpoint",100)
    visits=select("timepoints",80)
    row_values=vals(row_claims)
    stat_keys=unique(k for c in stats if (k:=statistic_kind(c["value"],style)) and k!="header")
    def exact_claim(label, cs):
        key=norm(label)
        return [c for c in cs if key and norm(c["value"])==key]
    def candidate_label(label, cs, path):
        hit=exact_claim(label,cs)
        return bound(path,tidy(label),hit) if hit else proposal(path,"[REVIEW] "+tidy(label))
    def proposed_text(label, cs, path):
        return candidate_label(label,cs,path)["value"]
    def evidence_list(path,cs,hint):
        values=vals(cs)
        if values and len(values)<=20:
            return bound(path,values,cs)
        return unresolved(path,hint)
    def proposed_list(path,values):
        return proposal(path,["[REVIEW] "+tidy(v) for v in values])
    def row_stats(path, raw, label):
        # Only link a statistic to a named row when the same exact quote
        # includes that row label. Otherwise keep approved layout options as proposals.
        related=[c for c in stats if norm(label) and (" "+norm(label)+" ") in (" "+norm(c["exact_quote"])+" ")]
        keys=unique(k for c in related if (k:=statistic_kind(c["value"],style)) and k!="header")
        if keys:
            return bound(path,keys,related)
        known=[k for k in raw if k in style["statistic_formats"] and k!="header"]
        return proposal(path,known,"Statistic rows are provisional library format suggestions; association to this variable not established.") if known else proposal(path,[UNKNOWN_KIND],"Statistic requirement not established.")
    blocks=[]
    defaults=preset.get("row_blocks",[])
    def block(bt,label,**extra):
        b={"block_id":f"B{len(blocks)+1}","block_type":bt,"label":label,**extra}
        blocks.append(b)
        return b
    def draft_items(raw, field_path):
        items=[]
        used=set()
        for item in raw:
            # Skip comparison-only rows until comparison structure is explicitly bound.
            if item.get("where") in ("comparison","both"):
                continue
            lab=re.sub(r"\{settings:[^}]+\}","[UNRESOLVED]",item["label"])
            hit=exact_claim(lab,row_claims+stats+endpoints)
            label=tidy(lab) if hit else "[REVIEW] "+tidy(lab)
            kind=item["kind"]
            if kind!="header" and kind not in style["statistic_formats"]:
                kind=UNKNOWN_KIND
            # An exact row label alone does not establish its statistic format.
            if kind!="header" and not any(statistic_kind(c["value"],style)==kind for c in hit):
                # Keep proposal format visible via row label, not a claimed SAP format.
                if not label.startswith("[REVIEW]"):
                    label="[REVIEW FORMAT] "+label
            if hit:
                bound(field_path+f"[{len(items)}]",tidy(lab),hit)
            items.append({"label":label,"indent":item.get("indent",0),"kind":kind,"where":"groups"})
            used.add(norm(lab))
        # Explicit unbound row/summary claims can be shown as candidate rows,
        # without pretending their statistic format is established.
        for c in row_claims+stats:
            label=tidy(c["value"])
            if norm(label) in used:
                continue
            used.add(norm(label))
            k=statistic_kind(label,style) if c["field"]=="statistics" else None
            bound(field_path+f"[{len(items)}]",label,[c])
            items.append({"label":"[CANDIDATE] "+label,"indent":0,
                          "kind":k if k and k!="header" else UNKNOWN_KIND,"where":"groups"})
        if not items:
            items=[{"label":"[UNRESOLVED] Confirm table rows and statistics","indent":0,"kind":UNKNOWN_KIND}]
        issue(field_path,"Confirm all proposed row labels, statistic formats and placement.","needs_review")
        return {"value":items,"source":"template_default","status":"needs_review",
                "note":"Mixed provisional structure and literal candidate rows; see adaptation audit."}

    if tid=="TBL_VARIABLE_SUMMARY":
        used=set()
        for raw in defaults:
            if raw["block_type"] not in ("continuous","categorical"):
                continue
            lab=raw["label"]
            path=f"row_blocks[{len(blocks)}]"
            label=candidate_label(lab,row_claims+endpoints,path+".label")
            used.add(norm(lab))
            # Even if variable name matches, type and row-specific format are provisional.
            if not label["value"].startswith("[REVIEW]"):
                label=dict(label,value="[CANDIDATE] "+label["value"])
            if raw["block_type"]=="continuous":
                b=block("continuous",label,statistics=row_stats(path+".statistics",raw.get("statistics",[]),lab))
                if raw.get("unit"):
                    b["unit"]=proposal(path+".unit","[REVIEW] "+raw["unit"])
            else:
                # Category values/cutoffs are not copied as study facts.
                cats=raw.get("categories",[])
                block("categorical",label,categories=proposed_list(path+".categories",cats or ["Category / levels to confirm"]),
                      missing_row=unresolved(path+".missing_row","Missing-category display"))
        extras=[c for c in row_claims if norm(c["value"]) not in used]
        if extras or not blocks:
            block("criterion",approved("Additional candidate rows"),
                  items=draft_items([],f"row_blocks[{len(blocks)}].items"))
    elif tid in ("TBL_CRITERION_COUNTS","TBL_TIME_TO_EVENT","TBL_RESPONSE_RATE","TBL_CONTINUOUS_COMPARISON"):
        raw=[item for b in defaults for item in b.get("items",[])]
        bt="criterion" if tid=="TBL_CRITERION_COUNTS" else "endpoint"
        block(bt,approved("Candidate endpoint / criterion rows"),
              items=draft_items(raw,"row_blocks[0].items"))
    elif tid=="TBL_CODED_TERM_HIERARCHY":
        raw=next((b for b in defaults if b["block_type"]=="coded_hierarchy"),{})
        anyrow=next((b for b in defaults if b["block_type"]=="any_row"),None)
        if anyrow:
            block("any_row",candidate_label(anyrow["label"],row_claims,"row_blocks[0].label"))
        path=f"row_blocks[{len(blocks)}]"
        levels=raw.get("levels") or ["Coding level to confirm"]
        block("coded_hierarchy",proposal(path+".label","[REVIEW] Coded terms"),
              levels=proposed_list(path+".levels",levels),
              dictionary=unresolved(path+".dictionary","Coding dictionary and version"))
    elif tid=="TBL_PARAMETER_BY_VISIT":
        raw=next(iter(defaults),{})
        params=evidence_list("row_blocks[0].parameters",row_claims,"Parameters to confirm") if row_values else proposed_list("row_blocks[0].parameters",raw.get("parameters") or ["Parameter to confirm"])
        vs=evidence_list("row_blocks[0].visits",visits,"Visits to confirm")
        if vs["value"] is None: vs["value"]=["[Visit to confirm]"]
        ct=raw.get("cell_type","continuous")
        extras={"parameters":params,"visits":vs,"cell_type":proposal("row_blocks[0].cell_type",ct),
                "change_from_baseline":unresolved("row_blocks[0].change_from_baseline","Whether change-from-baseline rows are required")}
        if ct=="continuous": extras["statistics"]=row_stats("row_blocks[0].statistics",raw.get("statistics",[]),"")
        else: extras["categories"]=proposed_list("row_blocks[0].categories",raw.get("categories") or ["Category to confirm"])
        block("parameter_visit",proposal("row_blocks[0].label","[REVIEW] Parameter by visit"),**extras)
    elif tid=="TBL_SHIFT_CROSSTAB":
        raw=next(iter(defaults),{})
        cats=raw.get("row_categories") or ["Row category to confirm"]
        columns["category_columns"]=proposed_list("columns.category_columns",preset.get("columns",{}).get("category_columns") or ["Column category to confirm"])
        block("crosstab",proposal("row_blocks[0].label","[REVIEW] Shift table"),
              row_variable=proposal("row_blocks[0].row_variable","[REVIEW] "+raw.get("row_variable","Row variable")),
              column_variable=proposal("row_blocks[0].column_variable","[REVIEW] "+raw.get("column_variable","Column variable")),
              row_categories=proposed_list("row_blocks[0].row_categories",cats),
              parameters=proposed_list("row_blocks[0].parameters",raw.get("parameters") or ["Parameter to confirm"]))
    elif tid=="TBL_TIMEPOINT_STATISTICS_COLUMNS":
        raw=next(iter(defaults),{})
        keys=stat_keys or [k for k in preset.get("columns",{}).get("statistic_columns",[]) if k in style["statistic_formats"]] or [UNKNOWN_KIND]
        columns["statistic_columns"]=proposal("columns.statistic_columns",keys,"Column statistic placement unconfirmed; confirm before use.")
        ts=evidence_list("row_blocks[0].timepoints",visits,"Timepoints to confirm")
        if ts["value"] is None: ts["value"]=["[Timepoint to confirm]"]
        block("timepoint_stats",proposal("row_blocks[0].label","[REVIEW] Timepoint summary"),
              parameters=proposed_list("row_blocks[0].parameters",raw.get("parameters") or ["Parameter to confirm"]),timepoints=ts)
    if not blocks:
        raise ValueError("No draft row blocks")

    # Render explicit candidate notes verbatim. Never construct analysis definitions
    # from placeholder syntax or transfer a preset's study-specific rule.
    footnotes=[]
    for f in ("denominator","confidence_intervals","missing_data","analysis_methods","footnotes"):
        cs=select(f,350)
        if cs:
            text="[CANDIDATE: "+f.replace("_"," ")+"] "+" | ".join(vals(cs))
            footnotes.append({"id":"E_"+f,"marker":None,"text":bound("footnotes."+f,text,cs)})
    for rule in template.get("skeleton",{}).get("footnotes",[]):
        if rule.get("only_if_config"): continue
        # Explicitly keep unresolved library requirements until independently mapped.
        footnotes.append({"id":rule["id"],"marker":rule.get("marker"),
                          "text":unresolved("footnotes["+rule["id"]+"]","Confirm "+rule["id"]+" study-specific definition")})
    # Preserve every retained claim in a sidecar; only render short relevant notes.
    notes=[{"id":"DRAFT_NOTICE","marker":None,"text":approved(
        "DRAFT - NOT CLINICALLY VALIDATED. [REVIEW] rows/format are template proposals; "
        "[CANDIDATE] values need scope confirmation. All numbers are placeholders. "
        "Group completeness, column layout, variable-specific statistics and missing requirements must be reviewed.")},
        {"id":"DRAFT_LAYOUT","marker":None,"text":approved(
        "Candidate template: "+tid+"; layout preset: "+str(pid or "none")+" ("+preset_basis+"). "
        "No final statistical programming or generation approval.")}]
    # Keep all study-specific gaps explicit, even when a chosen render layout
    # cannot express a required comparison or other library element.
    config={}
    if "comparison" in template.get("config_options",{}):
        config["comparison"]="none"
        issue("columns.comparison_columns","Confirm whether comparison columns/rows are needed; not rendered.","needs_review")
    if tid=="TBL_SHIFT_CROSSTAB": config["layout"]="matrix"
    for f in template["required_fields"]:
        if f["path"] not in ("title","population"):
            issue(f["path"],"Confirm required library field: "+f["label"],"needs_review")
    pg=style["page"]
    spec={"schema_version":"3.0","output_id":output_id,"output_type":"table",
          "template_id":tid,"template_version":template["version"],"preset_ids":[pid] if pid else [],
          "title":{"value":title,"source":"content_list","status":"resolved"},
          "population":population,"columns":columns,"row_blocks":blocks,"footnotes":footnotes,
          "programming_notes":notes,"config":config,
          "page":{k:pg[k] for k in ("orientation","paper","font","font_size_pt")} | {"include_programming_notes":True},
          "issues":issues,
          "provenance":{"content_list_entry":{"original_tfl_number":output_id,"original_title":title,"output_type":"table","source":"user_selected_target"},
             "template_file_sha256":library.templates[tid]["sha256"],
             "preset_file_sha256":{pid:library.presets[tid,pid]["sha256"]} if pid else {},
             "style_guide_version":style["version"],"study_settings_version":"unconfirmed-agent-candidates-v1",
             "match":{"selected":tid,"candidates":[{"template_id":t} for t in (result.get("matching") or {}).get("rank_prefix",[])],
                      "explanation":"Provisional agent recommendation; not confirmed. "+preset_basis},
             "generated_by":VERSION}}
    audit={"version":VERSION,"status":"unconfirmed_draft","tfl_id":output_id,
           "sap_sha256":result["sap_sha256"],"template_id":tid,"layout_preset":pid,"preset_basis":preset_basis,
           "matching_protocol_valid":result.get("matching_protocol_valid",False),
           "source_claims":claims,"bindings":bindings,"issues":issues,
           "notes":["Only retained literal claims are mapped; mapping is not independent semantic validation.",
                    "Template proposals remain visible and do not establish study-specific requirements.",
                    "The local draft-only statistic placeholder is not a change to the approved style guide.",
                    "Some extracted claims may remain only in this audit rather than in the table.",
                    "Comparison columns/rows are not automatically mapped in this initial adapter."],
           "clinical_confirmation":False,"generation_authorized":False,"new_llm_calls":0}
    return spec,audit,style

def generate_editable_draft(result, library, out):
    """Validate the spec, call the existing renderer, and check native Word tables.
    No previous ZIPs and no paid calls. Failure does not fabricate a fallback DOCX.
    """
    from jsonschema import Draft202012Validator
    from docx import Document
    out=Path(out)
    out.mkdir(parents=True,exist_ok=True)
    spec,audit,style=build_draft_spec(result,library)
    sp=out/"Adapted_Shell_Spec.json"
    ap=out/"Adaptation_Audit.json"
    style_path=out/"Draft_Render_Style.json"
    write_json(sp,spec)
    write_json(ap,audit)
    write_json(style_path,style)
    schema=read_json(library.safe_path("schemas/Shell_Spec.schema.json"))
    errors=list(Draft202012Validator(schema).iter_errors(spec))
    if errors:
        write_json(out/"Shell_Schema_Errors.json",[{"path":list(e.absolute_path),"message":e.message} for e in errors])
        raise ValueError("Adapted shell schema validation failed")
    renderer=library.safe_path("renderer/render_table.py").parent
    target=out/f"Generated_TFL_{spec['output_id']}.docx"
    tmp=out/f"Generated_TFL_{spec['output_id']}.tmp.docx"
    runner="import sys,json; sys.path.insert(0,sys.argv[1]); import render_table; render_table.render(json.load(open(sys.argv[2],encoding='utf-8')),json.load(open(sys.argv[3],encoding='utf-8')),sys.argv[4])"
    proc=subprocess.run([sys.executable,"-c",runner,str(renderer),str(sp),str(style_path),str(tmp)],
                        capture_output=True,text=True,timeout=120)
    if proc.returncode:
        write_json(out/"Render_Failure.json",{"returncode":proc.returncode,"stderr":proc.stderr[-4000:]})
        raise RuntimeError("Library table rendering failed")
    doc=Document(tmp)
    if not doc.tables or len(doc.tables[0].rows)<2 or len(doc.tables[0].columns)<2:
        raise ValueError("Generated document has no usable native Word table")
    texts=[p.text for p in doc.paragraphs]
    if "Table "+spec["output_id"] not in texts or spec["title"]["value"] not in texts:
        raise ValueError("Generated document identity mismatch")
    if not any("DRAFT - NOT CLINICALLY VALIDATED" in s for s in texts):
        raise ValueError("Draft warning missing")
    tmp.replace(target)
    info={"status":"editable_draft_generated","file":target.name,"sha256":sha_file(target),
          "schema_valid":True,"native_word_tables":len(doc.tables),
          "first_table_rows":len(doc.tables[0].rows),"first_table_columns":len(doc.tables[0].columns),
          "unresolved_or_review_issues":len(spec["issues"]),"mapped_evidence_bindings":len(audit["bindings"]),
          "rendered_study_specific_draft":True,"clinical_confirmation":False,"generation_authorized":False,
          "visual_render_review_complete":False,"new_llm_calls":0}
    write_json(out/"Generation_Summary.json",info)
    return info
