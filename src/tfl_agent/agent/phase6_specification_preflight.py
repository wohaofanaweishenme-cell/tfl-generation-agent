"""Phase 6.4 preflight only: prepare independent extraction and template context.
No LLM calls, no gold in extraction inputs, no claims inferred from templates.
"""
from pathlib import Path
import json
from tfl_agent.agent.phase6_simplified_replay import load_archive,normalize,ARCHIVE_SHA,digest

FIELDS={
    "analysis_population":"Explicit analysis set or population definition",
    "treatment_groups":"Treatment/group definitions and explicit grouping scope",
    "endpoint":"Target variable or endpoint and its definition",
    "timepoints":"Assessment timepoint, visit, window or reference point",
    "row_requirements":"Explicit target-specific row categories or hierarchy",
    "column_requirements":"Explicit target-specific column grouping or layout",
    "statistics":"Explicit statistics, counts, percentages, estimates, quantiles",
    "denominator":"Explicit denominator or handling of non-evaluable subjects",
    "analysis_methods":"Explicit method, model or comparison",
    "confidence_intervals":"Explicit CI level and method for the target",
    "missing_data":"Applicable missing data or censoring treatment",
    "footnotes":"Explicit target-specific reporting notes or definitions",
}
CONTRACT={"version":"phase64-preflight-v1","allowed_fields":FIELDS,
          "claim_fields":["field","value","source","chunk_id","exact_quote","applicability","reason"],
          "applicability":["target_specific","explicitly_applicable_study_rule","uncertain","not_applicable"],
          "rules":["A missing field is unknown, not absent by design.",
                   "The title can establish explicit target identity but is not SAP evidence.",
                   "SAP claims require exact source spans and a target applicability explanation.",
                   "Do not use a library preset as evidence of an analysis requirement.",
                   "General methods require explicit applicability to the target.",
                   "Conflicting claims remain unresolved; never auto-authorize generation."],
          "generation_authorized":False,"semantic_review_complete":False}

def prepare_specification_inputs(archive,out):
    req,raw,_,_=load_archive(archive)
    inputs=[]; context=[]
    for r in req:
        p=r["payload"]; rid=r["request_id"]
        obj=json.loads(raw[rid]["raw_response"])
        d=normalize(obj,p)
        # No matching result, expected label, preset or template defaults in extraction payload.
        payload={"target":p["target"],"sap_evidence":p["sap_evidence"],"allowed_fields":FIELDS}
        inputs.append({"request_id":rid,"study_id":r["study_id"],"entry_id":r["entry_id"],
                       "input_fingerprint":digest(payload),"payload":payload})
        context.append({"request_id":rid,"study_id":r["study_id"],"entry_id":r["entry_id"],
                        "rank_prefix":d["rank_prefix"],"unranked_templates":d["unranked_templates"],
                        "recommended_template":d["recommended_template"],"proposed_preset":d["proposed_preset"],
                        "protocol_supported_candidate":d["protocol_supported_template"],
                        "protocol_issues":d["issues"],"eligible_library_context":p["library"],
                        "confirmed_template":None,"semantic_applicability_verified":False,
                        "use":"Post-extraction comparison only; never a source of study facts."})
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    for name,value in (("Extraction_Inputs.json",inputs),("Template_Candidates.json",context),
                       ("Specification_Claim_Contract.json",CONTRACT),
                       ("Preflight_Summary.json",{"source_archive_sha256":ARCHIVE_SHA,"cases":len(inputs),
                       "new_llm_calls":0,"specifications_extracted":0,"generation_authorized":False,
                       "note":"Same development cases and matching-oriented retrieved chunks; field-specific retrieval coverage is not established."})):
        (out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return inputs,context
