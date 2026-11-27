"""Phase 6.4D: offline claim replay, conservative risk routing and field gap audit.
Never interprets literal validity as semantic validation. No LLM, no template labels.
"""
from __future__ import annotations
import csv, hashlib, io, json, re, zipfile
from collections import Counter
from pathlib import Path
from tfl_agent.agent.phase6_specification_pilot import (
    FIELDS, SYSTEM, MODEL, MAX_TOKENS, ARCHIVE_SHA as RETRIEVAL_SHA,
    audit_claims, validate_chunk, digest, save, csv_write)

ARCHIVE_NAME = "20261127T201349860244Z.zip"
ARCHIVE_SHA = "74d816887d611c7f53a0d4ed7b9d3e1416aa8ea72d84bf746fc64b0340097aaa"
VALID_CANDIDATES = {"evidence_backed_candidate", "title_explicit_candidate"}
GENERAL = re.compile(r"unless otherwise (?:stated|specified)|as appropriate|where applicable", re.I)

def load_frozen(path):
    b=Path(path).read_bytes()
    if hashlib.sha256(b).hexdigest()!=ARCHIVE_SHA:
        with zipfile.ZipFile(io.BytesIO(b)) as outer:
            found=[outer.read(n) for n in outer.namelist() if n.endswith("/"+ARCHIVE_NAME)]
        if len(found)!=1: raise ValueError("Expected one frozen inner archive")
        b=found[0]
    if hashlib.sha256(b).hexdigest()!=ARCHIVE_SHA: raise ValueError("Frozen successful pilot SHA mismatch")
    with zipfile.ZipFile(io.BytesIO(b)) as z:
        get=lambda n: json.loads(z.read(n))
        requests=get("Merge/Frozen_Extraction_Requests.json")
        responses=get("Extraction/Raw_Responses.json")
        cfg=get("Extraction/Experiment_Config.json")
        old=get("Extraction/Summary.json")
        specs=get("Extraction/Specification_Candidates.json")
        prior=list(csv.DictReader(io.StringIO(z.read("Extraction/Claim_Audit.csv").decode("utf-8-sig"))))
    if (cfg["archive_sha256"],cfg["model"],cfg["system"],cfg["max_tokens"],cfg["temperature"],cfg["thinking"],cfg["budget"])!=(RETRIEVAL_SHA,MODEL,SYSTEM,MAX_TOKENS,0,False,6):
        raise ValueError("Original config mismatch")
    if (old["parsed_responses"],old["claim_occurrences"],old["new_attempts_reserved"])!=(6,52,6): raise ValueError("Unexpected successful run")
    ids={r["request_id"] for r in requests}
    if len(requests)!=6 or len(ids)!=6 or len(responses)!=6 or {r["request_id"] for r in responses}!=ids or len(specs)!=6 or {r["request_id"] for r in specs}!=ids:
        raise ValueError("Case manifest mismatch")
    rr={r["request_id"]:r for r in responses}
    original={(r["request_id"],int(r["claim_index"])):r for r in prior}
    if len(original)!=52 or len(prior)!=52: raise ValueError("Claim manifest mismatch")
    replay=[]
    for r in requests:
        p=r["payload"]; rec=rr[r["request_id"]]
        fp=digest({"model":MODEL,"system":SYSTEM,"max_tokens":MAX_TOKENS,"temperature":0,"thinking":False,"payload":p})
        if fp!=r["fingerprint"] or fp!=rec["fingerprint"] or rec["status"]!="parsed" or rec["finish_reason"]!="stop":
            raise ValueError("Frozen response mismatch")
        if set(p)!={"target","allowed_fields","sap_evidence"} or p["allowed_fields"]!=FIELDS: raise ValueError("Unexpected extraction payload")
        cs=r["source_chunks"]
        if len(cs)!=len({c["chunk_id"] for c in cs}) or len(cs)!=len(p["sap_evidence"]): raise ValueError("Chunk identity mismatch")
        for c,m in zip(cs,p["sap_evidence"]):
            validate_chunk(c)
            if any(c[k]!=m[k] for k in ("chunk_id","section","pages","text")): raise ValueError("Chunk text mismatch")
        rows=audit_claims(json.loads(rec["raw_response"]),r)
        for a in rows:
            prev=original[(a["request_id"],a["claim_index"])]
            if json.loads(prev["raw_claim"])!=a["raw_claim"] or prev["status"]!=a["status"] or prev["exact_match"]!=str(a["exact_match"]) or prev["literal_support"]!=str(a["literal_support"]) or json.loads(prev["source_spans"])!=a["source_spans"]:
                raise ValueError("Phase6.4C replay mismatch")
        replay.extend(rows)
    if len(replay)!=52 or {(r["request_id"],r["claim_index"]) for r in replay}!=set(original): raise ValueError("Missing replay claims")
    return requests,replay,old

def risk_flags(row):
    """Reusable, deliberately narrow lexical flags; not a semantic classifier."""
    q=row.get("exact_quote") or ""; v=row.get("value") or ""; f=row.get("field")
    flags=[]
    if row["status"]=="rejected": flags.append("provenance_or_contract_failure")
    if row["status"]=="needs_review": flags.append("prior_uncertainty_or_location_ambiguity")
    if row.get("source")=="title": flags.append("title_only")
    if row.get("applicability")=="explicitly_applicable_study_rule": flags.append("verify_rule_scope")
    if GENERAL.search(q): flags.append("conditional_general_rule")
    if f=="confidence_intervals" and (GENERAL.search(q) or row.get("applicability")=="explicitly_applicable_study_rule"):
        flags.append("ci_convention_not_display_requirement")
    if f=="statistics" and v.strip().lower() in {"summary","summarized","summarised","tabulated"}: flags.append("unspecified_statistic")
    if f=="statistics" and re.search(r"decimal place|significant figure|rounding",q,re.I): flags.append("formatting_not_statistic")
    if f=="statistics" and re.search(r"^counted by\b",v,re.I): flags.append("counting_method_not_statistic")
    return flags

def route(row,flags):
    if row["status"]=="rejected": return "rejected"
    if row["status"] in {"duplicate","not_applicable"}: return row["status"]
    if row["status"]=="needs_review" or set(flags)&{"ci_convention_not_display_requirement","unspecified_statistic","formatting_not_statistic","counting_method_not_statistic","conditional_general_rule","verify_rule_scope"}:
        return "scope_or_field_review"
    return "unverified_candidate"

def assemble(request,rows,status_field,retain):
    """No new values. All statuses indicate candidates or unresolved gaps."""
    fields={}
    for f in FIELDS:
        relevant=[r for r in rows if r["field"]==f]
        kept=[r for r in relevant if r[status_field] in retain]
        values=list(dict.fromkeys(r["value"] for r in kept))
        fields[f]={"status":"candidate" if kept else "unresolved" if relevant else "unknown",
                   "values":values,"claim_indices":[r["claim_index"] for r in kept],
                   "other_claim_indices":[r["claim_index"] for r in relevant if r not in kept],
                   "multiple_values_require_scope_check":len(values)>1,
                   "requiredness":"undetermined"}
    return {"request_id":request["request_id"],"study_id":request["study_id"],"entry_id":request["entry_id"],
            "target":request["payload"]["target"],"sap_sha256":request["sap_sha256"],"fields":fields,
            "independent_semantic_validation_complete":False,"clinical_confirmation":False,"generation_authorized":False}

def run(path,out,annotations=None):
    requests,rows,old=load_frozen(path)
    lookup={r["request_id"]:r for r in requests}
    reviewed=[]; grouped={r["request_id"]:[] for r in requests}
    for r in rows:
        req=lookup[r["request_id"]]
        c=next((c for c in req["source_chunks"] if c["chunk_id"]==r["chunk_id"]),None)
        flags=risk_flags(r); decision=route(r,flags)
        item={**r,"original_status":r["status"],"risk_flags":flags,"rule_route":decision,
              "target_title":req["payload"]["target"]["title"],
              "source_section":c["section"] if c else None,"source_context":c["text"] if c else req["payload"]["target"]["title"] if r["source"]=="title" else None,
              "development_review":"unreviewed","development_reason":None}
        reviewed.append(item);grouped[r["request_id"]].append(item)
    # The manual development annotation set is explicitly separate from reusable routing.
    if annotations is not None:
        if annotations["source_archive_sha256"]!=ARCHIVE_SHA: raise ValueError("Annotation lineage mismatch")
        ann={(x["request_id"],x["claim_index"]):x for x in annotations["claims"]}
        if len(ann)!=len(annotations["claims"]) or set(ann)!={(r["request_id"],r["claim_index"]) for r in reviewed}: raise ValueError("Annotation identity mismatch")
        for r in reviewed:
            a=ann[r["request_id"],r["claim_index"]]
            # Archive digest and raw response index bind annotations to immutable claims.
            if a["request_id"]!=r["request_id"] or a["claim_index"]!=r["claim_index"]: raise ValueError("Annotation claim mismatch")
            if a["decision"] not in {"retain_candidate","context_only","needs_review","reject"} or not a["reason"]: raise ValueError("Invalid annotation")
            if a["decision"]=="retain_candidate" and r["original_status"] not in VALID_CANDIDATES: raise ValueError("Manual review cannot promote failed or ambiguous provenance")
            r["development_review"]=a["decision"];r["development_reason"]=a["reason"]
    rule_specs=[assemble(r,grouped[r["request_id"]],"rule_route",{"unverified_candidate"}) for r in requests]
    dev_specs=[assemble(r,grouped[r["request_id"]],"development_review",{"retain_candidate"}) for r in requests] if annotations is not None else []
    gaps=[]
    for s in dev_specs or rule_specs:
        for field,v in s["fields"].items():
            if v["status"]!="candidate" or v["multiple_values_require_scope_check"]:
                gaps.append({"request_id":s["request_id"],"target":s["target"]["title"],"field":field,
                             "status":v["status"],"values":v["values"],"requiredness":"undetermined",
                             "review_task":"scope_check_multiple_values" if v["multiple_values_require_scope_check"] else "check_if_required_and_evidence_available"})
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    report={"version":"6.4D-v1","source_archive_sha256":ARCHIVE_SHA,"new_llm_calls":0,"cases":6,
            "original_claims":len(rows),"original_status_counts":dict(Counter(r["status"] for r in rows)),
            "rule_route_counts":dict(Counter(r["rule_route"] for r in reviewed)),
            "risk_flag_counts":dict(Counter(f for r in reviewed for f in r["risk_flags"])),
            "development_review_counts":dict(Counter(r["development_review"] for r in reviewed)),
            "rule_field_counts":dict(Counter(f["status"] for s in rule_specs for f in s["fields"].values())),
            "development_field_counts":dict(Counter(f["status"] for s in dev_specs for f in s["fields"].values())),
            "independent_semantic_labels":0,"semantic_accuracy_established":False,"requiredness_validated":False,
            "generation_authorized":False,
            "caveats":["Manual development review is qualitative, not independent gold; no template labels used.",
                       "Lexical risk routing is not semantic validation and can miss scope errors.",
                       "Multiple values may be complementary, not contradictory. No automatic resolution.",
                       "Unknown/unresolved does not mean not applicable; field requiredness depends on target.",
                       "No rejected or ambiguous-provenance claim is promoted, and no new claim is generated."]}
    save(out/"Summary.json",report);save(out/"Rule_Only_Specifications.json",rule_specs)
    save(out/"Development_Reviewed_Specifications.json",dev_specs);save(out/"Claim_Review.json",reviewed)
    csv_write(out/"Claim_Review.csv",reviewed);csv_write(out/"Field_Gap_Review.csv",gaps)
    if annotations is not None: save(out/"Development_Gap_Notes.json",annotations.get("gap_notes",[]))
    return report
