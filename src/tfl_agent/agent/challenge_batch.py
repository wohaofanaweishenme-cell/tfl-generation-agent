"""Phase 5.2: predeclared challenge cohort, leakage preflight, paired batch evaluation."""
from __future__ import annotations
import csv
import hashlib
import json
import re
from pathlib import Path
from collections import defaultdict, Counter
from tfl_agent.agent.phase5_evaluation import row, aggregate
from tfl_agent.agent.sap_scope_pilot import run_scope_retrieval
from tfl_agent.agent.scoped_specification import run_specification_extraction
from tfl_agent.agent.phase4_pipeline import run_phase4
from tfl_agent.agent.sap_retrieval_pilot import _write_json, _write_csv
from tfl_agent.tools.sap_hybrid import LocalEncoder
from tfl_agent.tools.generic_library import load_generic_library


def read(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def read_csv(p):
    with Path(p).open(encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f))


def key(r):
    return r["study_id"],r["entry_id"]


def select_cohort(title_rows):
    """Freeze 21 baseline failures, additional hybrid regressions, 2 controls/study.

    Controls sampled deterministically by SHA-256 of study/entry, from cases
    correct under both title methods, same output type as most challenges (table).
    Labels and selection strata are never passed to the extraction/retrieval calls.
    """
    by=defaultdict(dict)
    for r in title_rows:
        if r["method"] in ("title_rule","title_keyword_dense_forced","title_dense_forced"):
            if r["method"] in by[key(r)]: raise ValueError("Duplicate benchmark row")
            by[key(r)][r["method"]]=r
    cohort=[]
    controls=defaultdict(list)
    for k,methods in sorted(by.items()):
        b=methods["title_rule"]; h=methods["title_keyword_dense_forced"]
        if any(m["expected"]!=b["expected"] or m["title"]!=b["title"] or m["output_type"]!=b["output_type"] for m in methods.values()):
            raise ValueError("Inconsistent benchmark identity")
        b_ok=b["correct"].lower()=="true"; h_ok=h["correct"].lower()=="true"
        case={f:b[f] for f in ("study_id","entry_id","output_id","output_type","title","expected","outcome")}
        if not b_ok: cohort.append({**case,"stratum":"baseline_failure"})
        elif not h_ok: cohort.append({**case,"stratum":"hybrid_regression"})
        elif b["output_type"]=="table" and b["expected"]!="NONSTANDARD":
            controls[k[0]].append(case)
    for study,cases in sorted(controls.items()):
        ordered=sorted(cases,key=lambda c:hashlib.sha256(("phase52-control-v1|"+study+"|"+c["entry_id"]).encode()).hexdigest())
        cohort.extend({**c,"stratum":"control"} for c in ordered[:2])
    return sorted(cohort,key=lambda c:(c["study_id"],c["stratum"],c["entry_id"]))


def preflight(root,cohort,out):
    """Local PDF page previews, no network or LLM. Registry bounds are upper limits,
    NOT proof that preceding pages are statistical body. Every run needs approved bounds."""
    import pymupdf
    root,out=Path(root),Path(out)
    out.mkdir(parents=True,exist_ok=True)
    configs=[]; page_rows=[]; mapping_rows=[]
    lib=load_generic_library(root/"generic_template_library")
    for study in sorted({c["study_id"] for c in cohort}):
        reg=root/"library/studies"/study/"source_registry"
        content=read(reg/"Content_List.json")["entries"]
        manifest=read(reg/"Shell_Manifest.json")
        entries={e["entry_id"]:e for e in content}
        mappings={m["entry_id"]:m for m in manifest["content_list_mappings"]}
        for c in [c for c in cohort if c["study_id"]==study]:
            e=entries[c["entry_id"]]; m=mappings.get(c["entry_id"],{})
            expected_types=sorted({lib.templates[t]["output_type"] for t in c["expected"].split("|") if t in lib.templates})
            mapping_rows.append({**c,"registry_title_matches":e["original_title"]==c["title"],
                "registry_type_matches":e["output_type"]==c["output_type"],
                "relation":m.get("relation"),"mapping_review_status":m.get("review_status"),
                "expected_template_types":"|".join(expected_types),
                "type_conflict":bool(expected_types and c["output_type"] not in expected_types)})
        docs=sorted((root/"library/studies"/study/"original").glob("*.pdf"))
        for pdf in docs:
            # Registry document IDs must match filename. Alternate copies are not interchangeable.
            docids={r["document_id"] for e in content for r in e.get("source_regions",[])}
            matched=[d for d in docids if pdf.name.startswith(d+" ") or pdf.stem==d]
            if len(matched)!=1: continue
            docid=matched[0]
            cp=[r["pdf_page"] for e in content for r in e.get("source_regions",[]) if r["document_id"]==docid]
            sp=[r["pdf_page"] for e in manifest["shells"] for r in e.get("source_regions",[]) if r["document_id"]==docid]
            if not cp or not sp: continue
            cap=min(min(cp),min(sp))-1
            digest=hashlib.sha256(pdf.read_bytes()).hexdigest()
            with pymupdf.open(str(pdf)) as d:
                for page in range(1,min(cap,len(d))+1):
                    text=" ".join(d[page-1].get_text().split())
                    terms=[x for x in ("statistical analysis","analysis population","analysis set","adverse event","efficacy","missing data","descriptive statistics","treatment group","kaplan") if x in text.lower()]
                    page_rows.append({"study_id":study,"pdf":pdf.name,"page":page,"words":len(text.split()),
                                      "statistical_terms":"|".join(terms),"preview":text[:700]})
                configs.append({"study_id":study,"pdf_path":str(pdf.relative_to(root)),"sha256":digest,
                                "pdf_pages":len(d),"first_content_list_page":min(cp),"first_shell_page":min(sp),
                                "max_body_page":cap,"body_first":None,"body_last":None,
                                "body_verified":False,"api_authorized":False,
                                "note":"Choose one PDF per study; confirm physical statistical-body range from original PDF, not keywords alone."})
    _write_json(out/"Study_Preflight.json",configs)
    _write_csv(out/"Page_Review.csv",page_rows,["study_id","pdf","page","words","statistical_terms","preview"])
    _write_csv(out/"Mapping_Review.csv",mapping_rows,list(mapping_rows[0]))
    _write_csv(out/"Cohort.csv",cohort,list(cohort[0]))
    return configs,mapping_rows


# Candidate ranges reviewed from the first preflight's page previews.
# These are bound to exact PDF hashes, not a blanket approval or full-page review.
PREFERRED_BODIES = {
    "ARV-471-BC-201": ("ac6ebc7497c8ea2d5ffd31834e02f95206884f7ac54e69e54a3cf7f9f4cd8caf", 10, 30),
    "OMO-103-01": ("1aa3f12d5e1f3fba31e789edc9911b3dfb4622e3940c79acfab56a074b04255a", 8, 29),
    "SP11631": ("513b744f284eca557817ab39dd036972ff6b1e5e12ff924b71a56646168c55f7", 5, 27),
}

def preferred_configs(preflight_rows, *, body_verified=False, api_authorized=False):
    configs=[]
    for study,(digest,first,last) in PREFERRED_BODIES.items():
        matches=[r for r in preflight_rows if r["study_id"]==study and r["sha256"]==digest]
        if len(matches)!=1:
            raise ValueError(f"Expected exactly one matching preflight PDF for {study}")
        r=matches[0]
        if last>min(r["max_body_page"],r["pdf_pages"]):
            raise ValueError(f"Preferred body exceeds registry bounds: {study}")
        configs.append({"study_id":study,"pdf_path":r["pdf_path"],"sha256":digest,
                        "body_first":first,"body_last":last,
                        "body_verified":body_verified,"api_authorized":api_authorized})
    return configs

def validate_config(root,config,preflight_rows):
    if not config.get("body_verified") or not config.get("api_authorized"):
        raise ValueError("Body range and API authorization not confirmed")
    original=next((r for r in preflight_rows if r["study_id"]==config["study_id"] and r["pdf_path"]==config["pdf_path"]),None)
    if original is None: raise ValueError("PDF not in preflight registry")
    if config.get("sha256",original["sha256"])!=original["sha256"]: raise ValueError("Configured PDF hash mismatch")
    pdf=(Path(root)/original["pdf_path"]).resolve()
    if not pdf.is_relative_to(Path(root).resolve()/"library/studies"): raise ValueError("Unsafe PDF path")
    if hashlib.sha256(pdf.read_bytes()).hexdigest()!=original["sha256"]: raise ValueError("PDF changed after preflight")
    first,last=config["body_first"],config["body_last"]
    if type(first) is not int or type(last) is not int or not 1<=first<=last<=min(original["max_body_page"],original["pdf_pages"]):
        raise ValueError("Page range reaches Content List/shell or is invalid")
    preferred=PREFERRED_BODIES.get(config["study_id"])
    if preferred and original["sha256"]==preferred[0] and not preferred[1]<=first<=last<=preferred[2]:
        raise ValueError("Range outside reviewed candidate body boundaries")
    return pdf,(first,last)


def run_batch(root,cohort,title_rows,preflight_rows,mapping_rows,configs,out,llm=None,encoder=None):
    """All planned cases tracked. Evaluate paired completed subset and attempted
    operational success separately. No claims from expected label or source shells."""
    root,out=Path(root),Path(out)
    out.mkdir(parents=True,exist_ok=True)
    configmap={}
    for c in configs:
        if c["study_id"] in configmap: raise ValueError("Choose only one PDF per study")
        configmap[c["study_id"]]=c
    titlemap=defaultdict(dict)
    for r in title_rows: titlemap[key(r)][r["method"]]=r
    mapping={key(r):r for r in mapping_rows}
    status=[]; results=[]; enc=encoder
    _write_json(out/"Run_Config.json",configs)
    study_reports=[]
    for study in sorted({c["study_id"] for c in cohort}):
        cases=[c for c in cohort if c["study_id"]==study]
        config=configmap.get(study)
        if config is None or not config.get("body_verified") or not config.get("api_authorized"):
            detail="study_not_selected" if config is None else "body_or_api_confirmation_pending"
            status.extend({**c,"status":"skipped_unverified_body_or_permission","detail":detail} for c in cases)
            continue
        try: pdf,pages=validate_config(root,config,preflight_rows)
        except ValueError as e:
            status.extend({**c,"status":"skipped_invalid_configuration","detail":str(e)} for c in cases)
            continue
        eligible=[]
        for c in cases:
            m=mapping[key(c)]
            if not m["registry_title_matches"] or not m["registry_type_matches"] or m["relation"]!="direct_shell" or m["mapping_review_status"]!="verified":
                status.append({**c,"status":"skipped_mapping_unverified","detail":""})
            else: eligible.append(c)
        if not eligible: continue
        if llm is None: raise ValueError("An authorized LLM client is required for configured studies")
        study_out=out/"Studies"/study
        stage="encoder_initialization"
        # Use unique registry IDs internally (physical TFL numbers can repeat).
        # Target title/type only; expected labels never enter the prompts.
        targets=[{"tfl_id":c["entry_id"],"title":c["title"],"output_type":c["output_type"]} for c in eligible]
        try:
            if enc is None: enc=LocalEncoder()
            stage="sap_retrieval"
            print(f"{study}: retrieving evidence for {len(targets)} targets",flush=True)
            run_scope_retrieval(pdf,pages,targets,study_out/"Retrieval",encoder=enc,compare_phase2=False)
            stage="specification_extraction"
            print(f"{study}: extracting requirements",flush=True)
            phase3_summary,_,_=run_specification_extraction(study_out/"Retrieval",study_out,llm,encoder=enc)
            study_reports.append({"study_id":study,"phase3_llm_calls":phase3_summary["llm_calls"],"phase3_completed":True})
            stage="template_retrieval"
            _,rr,_=run_phase4(study_out,root/"generic_template_library",study_out/"Phase4",encoder=enc)
            byid={r["identity"]["tfl_id"]:r for r in rr}
        except Exception as e:
            # API exception text may contain sensitive payload; only class recorded.
            status.extend({**c,"status":"attempt_failed","detail":stage+":"+type(e).__name__} for c in eligible)
            _write_json(out/"Case_Status.json",status)
            continue
        for c in eligible:
            r=byid.get(c["entry_id"])
            if r is None:
                status.append({**c,"status":"attempt_failed","detail":"missing_result"})
                continue
            status.append({**c,"status":"completed","detail":"type_conflict_in_registry" if mapping[key(c)]["type_conflict"] else ""})
            for name in ("title_rule","title_dense_forced","title_keyword_dense_forced"):
                old=titlemap[key(c)][name]
                results.append(row(name,c,old["ranking"].split("|") if old["ranking"] else [],old["selected"] or None,old["selected_preset"] or None))
            ranking=r["ablation_rankings"]["keyword_dense_no_structure"]
            results.append(row("sap_keyword_dense_forced",c,ranking,ranking[0] if ranking else None))
            viable=[x["template_id"] for x in r["candidates"] if not x["structural_conflict"]]
            results.append(row("sap_aware",c,viable,r["template_id"],r["preset_id"]))
        _write_json(out/"Case_Status.json",status)
        if results: _write_csv(out/"Paired_Results.csv",results,list(results[0]))
    if results: _write_csv(out/"Paired_Results.csv",results,list(results[0]))
    _write_json(out/"Case_Status.json",status)
    attempted=sum(s["status"] in ("completed","attempt_failed") for s in status)
    completed=sum(s["status"]=="completed" for s in status)
    success=sum(r["correct"] for r in results if r["method"]=="sap_aware")
    consistent=[r for r in results if not mapping[key(r)]["type_conflict"]]
    conflicts=[r for r in results if mapping[key(r)]["type_conflict"]]
    if consistent: _write_csv(out/"Paired_Type_Consistent.csv",consistent,list(consistent[0]))
    if conflicts: _write_csv(out/"Paired_Type_Conflict.csv",conflicts,list(conflicts[0]))
    configured_cases=[c for c in cohort if c["study_id"] in configmap]
    consistent_status=[r for r in status if not mapping[key(r)]["type_conflict"]]
    consistent_attempted=sum(r["status"] in ("completed","attempt_failed") for r in consistent_status)
    consistent_success=sum(r["correct"] for r in consistent if r["method"]=="sap_aware")
    report={"configured_case_count":len(configured_cases),
            "configured_type_consistent_count":sum(not mapping[key(c)]["type_conflict"] for c in configured_cases),
            "configured_type_conflict_count":sum(mapping[key(c)]["type_conflict"] for c in configured_cases),
            "paired_type_consistent_metrics":aggregate(consistent),
            "paired_type_conflict_metrics":aggregate(conflicts),
            "type_consistent_attempted":consistent_attempted,
            "type_consistent_operational_success":consistent_success/consistent_attempted if consistent_attempted else None,
            "completed_phase3_llm_calls":sum(r["phase3_llm_calls"] for r in study_reports),
            "study_reports":study_reports,
            "planned":len(cohort),"strata":dict(Counter(c["stratum"] for c in cohort)),
            "status_counts":dict(Counter(s["status"] for s in status)),
            "attempted":attempted,"completed":completed,
            "sap_aware_operational_success":success/attempted if attempted else None,
            "paired_completed_metrics":aggregate(results),
            "paired_by_stratum":{s:aggregate([r for r in results if r["stratum"]==s]) for s in sorted({c["stratum"] for c in cohort})},
            "evaluation_status":"in-library development diagnostic; not held-out generalization",
            "warnings":["Skipped cases excluded from paired metrics, listed in Case_Status.json.",
                        "Attempt failures count against operational success, not against rank metrics.",
                        "Registry output-type conflicts preserved, not corrected using gold labels.",
                        "Forced methods have different abstention policies.",
                        "No clinical correctness or preset accuracy asserted."]}
    _write_json(out/"Summary.json",report)
    return report
