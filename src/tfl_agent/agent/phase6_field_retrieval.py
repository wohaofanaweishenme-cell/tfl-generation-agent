"""Phase 6.4B: field-oriented SAP retrieval, fixed development cohort, no LLM.
No gold, library, historical claims or topic hard filters enter retrieval.
Historical quote overlap is a diagnostic, not independent evidence recall.
"""
from __future__ import annotations
import csv, io, json, hashlib, zipfile
from pathlib import Path
from collections import defaultdict, Counter
from tfl_agent.agent.phase6_specification_preflight import FIELDS
from tfl_agent.agent.phase6_simplified_replay import ARCHIVE_SHA as PILOT_SHA, digest
from tfl_agent.agent.phase6_common import cases, study_artifacts, verify_identity, extract_phase52
from tfl_agent.tools.sap_hybrid import Chunk, Span, HybridSAPIndex

PREFLIGHT_NAME="20261127T190148681515Z.zip"
PREFLIGHT_SHA="4e52367c4d70d45c5df7b9619eb062887c314205fa41d0b7b99492298a7ba63d"
HISTORICAL_NAME="20261127T021948099654Z.zip"
HISTORICAL_SHA="7418f09c9993b0ab505c791c36d7fadf9f60eb88966294a3ee102cbcafaafcbf"
MODEL="BAAI/bge-small-en-v1.5"
TOP_K=8
DEPTH=20
MAX_CHUNKS=20
MAX_CHARS=24000
GROUPS={
    "population_grouping":("analysis_population","treatment_groups","column_requirements"),
    "endpoint_time":("endpoint","timepoints"),
    "presentation":("row_requirements","statistics"),
    "methodology":("analysis_methods","denominator","confidence_intervals","missing_data"),
    "reporting":("footnotes",),
}
# Target-conditioned and context-oriented searches are tagged separately.
# Generic context is retrieved as a possibility, never automatically applicable.
QUERIES={
    "population_grouping":[("target","analysis population analysis set patients treatment groups columns by arm"),
                           ("context","analysis populations definitions treatment groups randomization arms analysis sets")],
    "endpoint_time":[("target","endpoint variable definition measurement assessment timepoint visit window"),
                     ("target","assessment schedule baseline post baseline timepoint evaluation definition")],
    "presentation":[("target","summary table categories variables rows grouping hierarchy counts frequency descriptive statistics"),
                    ("target","statistics displayed number percentage mean standard deviation median minimum maximum distribution")],
    "methodology":[("target","statistical analysis method denominator confidence interval missing data non-evaluable censoring"),
                   ("context","general statistical methods denominator conventions missing data confidence intervals unless otherwise specified")],
    "reporting":[("target","table footnote reporting notes definitions abbreviations presentation conventions"),
                 ("context","general reporting conventions table footnotes rounding decimal places abbreviations")],
}
FIELD_MAP={
    "analysis_population":"analysis_population","endpoint_name":"endpoint","endpoint_definition":"endpoint",
    "analysis_methods":"analysis_methods","variables_to_display":"row_requirements",
    "statistics_to_display":"statistics","row_requirements":"row_requirements","column_requirements":"column_requirements",
    "grouping_basis":"column_requirements","subgroup_requirements":"column_requirements",
    "denominator_rule":"denominator","footnote_requirements":"footnotes","censoring_rules":"missing_data",
    "comparison_requirements":"analysis_methods","timepoints":"timepoints","ci_methods":"confidence_intervals",
}

def sha_file(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

def query_plan(target):
    title=target["title"].strip()
    if not title: raise ValueError("Empty title")
    if set(f for fs in GROUPS.values() for f in fs)!=set(FIELDS): raise ValueError("Field mapping drift")
    return [{"facet":f"{g}:{i+1}","group":g,"query_scope":scope,
             "fields":list(GROUPS[g]),"query":f"{title} {hint}" if scope=="target" else hint}
            for g in GROUPS for i,(scope,hint) in enumerate(QUERIES[g])]

def load_preflight(path):
    if sha_file(path)!=PREFLIGHT_SHA: raise ValueError("Frozen preflight archive hash mismatch")
    with zipfile.ZipFile(path) as z:
        inputs=json.loads(z.read("Phase64_Preflight/Extraction_Inputs.json"))
        summary=json.loads(z.read("Phase64_Preflight/Preflight_Summary.json"))
    if summary["source_archive_sha256"]!=PILOT_SHA or summary["cases"]!=6 or summary["specifications_extracted"]!=0:
        raise ValueError("Preflight lineage mismatch")
    if len(inputs)!=6 or len({(x["study_id"],x["entry_id"]) for x in inputs})!=6:
        raise ValueError("Expected six unique cases")
    for x in inputs:
        p=x["payload"]
        if set(p)!={"target","sap_evidence","allowed_fields"} or p["allowed_fields"]!=FIELDS or digest(p)!=x["input_fingerprint"]:
            raise ValueError("Extraction input mismatch")
        if x["request_id"]!=f'{x["study_id"]}__{x["entry_id"]}__D_applicability':
            raise ValueError("Case ID mismatch")
    return inputs

def rank_groups(results):
    """RRF over the two hybrid rankings per group; preserve per-query hits."""
    scores={g:defaultdict(float) for g in GROUPS}
    hitmap=defaultdict(list)
    seen=set()
    for q in results:
        g=q["group"]; facet=q["facet"]
        if g not in GROUPS or facet in seen: raise ValueError("Invalid query results")
        seen.add(facet)
        ids=set()
        for hit in q["methods"]["hybrid"]:
            cid=hit["chunk_id"]
            if cid in ids: raise ValueError("Duplicate query hit")
            ids.add(cid)
            scores[g][cid]+=1/(60+hit["rank"])
            hitmap[cid].append({"group":g,"facet":facet,"query_scope":q["query_scope"],**hit})
    expected={f"{g}:{i+1}" for g in GROUPS for i in range(len(QUERIES[g]))}
    if seen!=expected: raise ValueError("Incomplete query results")
    ranked={g:sorted(scores[g],key=lambda c:(-scores[g][c],c)) for g in GROUPS}
    return ranked,hitmap

def allocate(ranked,records,max_chunks,max_chars=None):
    """Round robin over groups with ID dedup. No text truncation or fabricated spans.
    A duplicate already chosen by a previous group is skipped, so each group
    gets a chance to contribute a new chunk before the next round.
    """
    if max_chunks<0 or (max_chars is not None and max_chars<0): raise ValueError("Invalid budget")
    picked=[]; seen=set(); cursor={g:0 for g in GROUPS}; used=0
    contributions={g:[] for g in GROUPS}
    while len(picked)<max_chunks:
        progress=False
        for g in GROUPS:
            while cursor[g]<len(ranked[g]):
                cid=ranked[g][cursor[g]]; cursor[g]+=1
                if cid in seen: continue
                cost=len(records[cid]["text"])
                if max_chars is not None and used+cost>max_chars: continue
                picked.append(cid); seen.add(cid); used+=cost; contributions[g].append(cid);progress=True
                break
            if len(picked)>=max_chunks: break
        if not progress: break
    return picked,contributions

def _source_record(c):
    return {k:c[k] for k in ("chunk_id","section","pages","text","source_spans")}

def _write_csv(path,rows,fields=None):
    fields=fields or list(dict.fromkeys(k for r in rows for k in r))
    with Path(path).open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore");w.writeheader()
        for r in rows: w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else v for k,v in r.items()})

def _save(path,value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

def historical_overlap(spec,record_map,arms,identity):
    """Only after retrieval. Unique target claims with verified original quotes.
    Accepted vs review status retained; no assertion that claims are correct.
    """
    refs={}
    for status,key in (("accepted","claims"),("needs_review","review_claims")):
        for c in spec.get(key,[]):
            field=FIELD_MAP.get(c["field"])
            if field is None: continue
            cid=c["chunk_id"]; quote=c["exact_quote"]
            if cid not in record_map or not isinstance(quote,str) or not quote.strip() or quote not in record_map[cid]["text"]:
                raise ValueError("Historical quote provenance mismatch")
            k=(c["field"],c["value"],cid,quote)
            if k not in refs: refs[k]={"historical_statuses":[],"field":field}
            if status not in refs[k]["historical_statuses"]: refs[k]["historical_statuses"].append(status)
    out=[]
    for (old_field,value,cid,quote),v in refs.items():
        row={**identity,"old_field":old_field,"field":v["field"],"value":value,
             "source_chunk_id":cid,"exact_quote":quote,"historical_statuses":v["historical_statuses"],
             "semantic_label":"unreviewed"}
        for name,ids in arms.items():
            row[name+"_chunk_hit"]=cid in ids
            row[name+"_quote_hit"]=any(quote in record_map[i]["text"] for i in ids)
        out.append(row)
    return out

def run_field_retrieval(preflight_zip,historical_zip,cache_dir,out,encoder):
    inputs=load_preflight(preflight_zip)
    if sha_file(historical_zip)!=HISTORICAL_SHA: raise ValueError("Phase52 hash mismatch")
    root=extract_phase52(historical_zip,cache_dir)
    manifest={(r["study_id"],r["entry_id"]):r for r in cases(root)}
    stores={}; indexes={}; packages=[]; queries=[]; budget=[]; coverage=[]; pool=[]; overlaps=[]
    for x in inputs:
        study=x["study_id"]; entry=x["entry_id"]; p=x["payload"]; rid=x["request_id"]
        if study not in stores:
            stores[study]=study_artifacts(root,study)
        store,chunks,parts,specs,summary=stores[study]
        case=manifest[study,entry]
        ident=verify_identity(case,parts[entry],specs[entry])
        if case["type_conflict"] or p["target"]!={"title":ident["title"],"output_type":ident["output_type"]}:
            raise ValueError("Frozen target mismatch")
        records={c["chunk_id"]:c for c in chunks}
        if len(records)!=len(chunks): raise ValueError("Duplicate chunk IDs")
        baseline=[]
        for c in p["sap_evidence"]:
            original=records[c["chunk_id"]]
            if any(original[k]!=c[k] for k in ("section","pages","text")):
                raise ValueError("Matching evidence differs from verified SAP body")
            baseline.append(c["chunk_id"])
        if len(baseline)!=len(set(baseline)): raise ValueError("Duplicate baseline evidence")
        if study not in indexes:
            cs=[Chunk(c["chunk_id"],c["section"],tuple(c["pages"]),c["text"],
                      tuple(Span(**s) for s in c["spans"])) for c in chunks]
            indexes[study]=HybridSAPIndex(cs,encoder)
        plans=query_plan(p["target"])
        results=indexes[study].search(plans,top_k=TOP_K,depth=DEPTH)
        ranked,hitmap=rank_groups(results)
        for q in results:
            queries.append({"request_id":rid,"study_id":study,"entry_id":entry,**q})
        matched,mc=allocate(ranked,records,len(baseline))
        expanded,ec=allocate(ranked,records,MAX_CHUNKS,MAX_CHARS)
        arms={"matching_baseline":baseline,"field_count_matched":matched,"field_expanded":expanded}
        identity={"request_id":rid,"study_id":study,"entry_id":entry,"title":p["target"]["title"]}
        for name,ids in arms.items():
            # Query membership is a routing signal only; not semantic field coverage.
            evidence=[_source_record(records[cid]) for cid in ids]
            payload={"target":p["target"],"sap_evidence":evidence,"allowed_fields":FIELDS}
            packages.append({**identity,"arm":name,"sap_sha256":summary["sap_sha256"],
                             "input_fingerprint":digest(payload),"payload":payload,
                             "generation_authorized":False})
            budget.append({**identity,"arm":name,"chunks":len(ids),"chars":sum(len(records[i]["text"]) for i in ids),
                           "words":sum(len(records[i]["text"].split()) for i in ids),
                           "overlap_with_matching":len(set(ids)&set(baseline)),
                           "new_vs_matching":len(set(ids)-set(baseline))})
            for g in GROUPS:
                ghits=[i for i in ids if i in ranked[g]]
                contributions=(mc if name=="field_count_matched" else ec if name=="field_expanded" else {}).get(g,[])
                coverage.append({**identity,"arm":name,"group":g,"fields":list(GROUPS[g]),
                                 "group_candidate_hits":len(ghits),"allocated_new_chunks":len(contributions),
                                 "candidate_ids":ghits,"semantic_coverage":None})
        for cid in sorted(set(baseline)|set(hitmap)):
            c=records[cid]
            pool.append({**identity,"chunk_id":cid,"section":c["section"],"pages":c["pages"],
                         "text":c["text"],"source_spans":c["source_spans"],
                         "groups":[g for g in GROUPS if cid in ranked[g]],"query_hits":hitmap[cid],
                         **{name+"_selected":cid in ids for name,ids in arms.items()},
                         "semantic_applicability":"unreviewed","supported_fields":"unreviewed"})
        overlaps.extend(historical_overlap(specs[entry],records,arms,identity))
        print("Retrieved:",study,entry,"| matching/matched/expanded:",*(len(ids) for ids in arms.values()),flush=True)
    names=("matching_baseline","field_count_matched","field_expanded")
    metrics={}
    for arm in names:
        bs=[r for r in budget if r["arm"]==arm]
        cov=[r for r in coverage if r["arm"]==arm]
        metrics[arm]={"cases":len(bs),"chunk_occurrences":sum(r["chunks"] for r in bs),
                      "characters":sum(r["chars"] for r in bs),"words":sum(r["words"] for r in bs),
                      "group_membership_nonempty":sum(r["group_candidate_hits"]>0 for r in cov),
                      "group_membership_total":len(cov),
                      "historical_target_claims":len(overlaps),
                      "historical_chunk_hits":sum(r[arm+"_chunk_hit"] for r in overlaps),
                      "historical_quote_hits":sum(r[arm+"_quote_hit"] for r in overlaps),
                      "historical_accepted_quote_hits":sum(r[arm+"_quote_hit"] and "accepted" in r["historical_statuses"] for r in overlaps),
                      "historical_accepted_claims":sum("accepted" in r["historical_statuses"] for r in overlaps)}
    report={"version":"6.4B-v1","new_llm_calls":0,"cases":len(inputs),"studies":len(indexes),
            "encoder":getattr(encoder,"model_name",type(encoder).__name__),
            "queries_per_case":len(query_plan(inputs[0]["payload"]["target"])),
            "query_top_k":TOP_K,"query_depth":DEPTH,"expanded_max_chunks":MAX_CHUNKS,"expanded_max_characters":MAX_CHARS,
            "metrics":metrics,"candidate_review_rows":len(pool),"independent_field_labels":0,
            "specifications_extracted":0,"generation_authorized":False,
            "source_sha256":{"preflight":PREFLIGHT_SHA,"historical":HISTORICAL_SHA},
            "caveats":["Six development tables, not held-out.",
                       "Count-matched is chunk-count matched when sufficient candidates exist, not word/token matched.",
                       "Expanded budget measures retrieval plus increased context, not isolated retrieval quality.",
                       "Group membership is query retrieval overlap, not verified field coverage.",
                       "Historical target-claim overlap is not independent recall; review claims may be inapplicable.",
                       "Exact quotes in normalized SAP chunks do not establish target applicability.",
                       "No library or historical claims used in inference; historical claims joined only after selection."]}
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    _save(out/"Summary.json",report)
    _save(out/"Field_Query_Results.json",queries)
    _save(out/"Extraction_Evidence_Packages.json",packages)
    _write_csv(out/"Evidence_Budget.csv",budget)
    _write_csv(out/"Field_Group_Coverage.csv",coverage)
    _write_csv(out/"Pooled_Evidence_Review.csv",pool)
    _write_csv(out/"Historical_Claim_Overlap.csv",overlaps,fields=list(overlaps[0]) if overlaps else ["request_id","field","exact_quote"])
    return report,packages
