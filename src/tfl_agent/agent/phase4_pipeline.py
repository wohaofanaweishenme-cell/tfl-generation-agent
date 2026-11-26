"""Run Phase 4 from a saved Phase 3 artifact, without calling an LLM."""
from pathlib import Path
import json
from tfl_agent.agent.scoped_specification import EvidenceStore
from tfl_agent.agent.requirement_normalizer import normalize_spec
from tfl_agent.agent.sap_aware_retriever import SAPAwareRetriever, gap_analysis
from tfl_agent.tools.generic_library import load_generic_library
from tfl_agent.tools.sap_hybrid import LocalEncoder
from tfl_agent.agent.sap_retrieval_pilot import _write_json, _write_csv


def read(p):
    return json.loads(p.read_text(encoding="utf-8"))


def run_phase4(phase3_dir, library_path, out_dir, *, encoder=None):
    src,out=Path(phase3_dir),Path(out_dir)
    out.mkdir(parents=True,exist_ok=True)
    study=read(src/"Study_Settings.json")
    specs=read(src/"TFL_Requirements.json")
    summary=read(src/"Summary.json")
    ret=src/"Retrieval"
    ret_summary=read(ret/"Summary.json")
    hashes={summary["sap_sha256"],study["sap_sha256"],ret_summary["sap_sha256"],*(s["sap_sha256"] for s in specs)}
    if len(hashes)!=1: raise ValueError("Mixed SAP artifacts")
    if not specs: raise ValueError("No target requirements")
    if study.get("clinical_confirmation") is not False or any(s.get("clinical_confirmation") is not False for s in specs):
        raise ValueError("Expected Phase 3 candidate artifacts")
    store=EvidenceStore(read(ret/"SAP_Blocks.json"),read(ret/"Scoped_Chunks.json"))
    package=read(ret/"Evidence_Package.json")
    parts={p["target"]["tfl_id"]:p for p in package["targets"]}
    for s in [study,*specs]:
        for c in s["claims"]:
            if c["status"]!="evidence_backed_candidate" or store.locate(c["chunk_id"],c["exact_quote"])!=c["source_spans"]:
                raise ValueError("Invalid candidate claim provenance")
    library=load_generic_library(library_path)
    retriever=SAPAwareRetriever(library,encoder if encoder is not None else LocalEncoder())
    normalized,results,plans,rows=[],[],[],[]
    for spec in specs:
        ident=spec["identity"]
        part=parts[ident["tfl_id"]]
        if part["target"]["title"]!=ident["title"]:
            raise ValueError("Target title mismatch")
        for c in part["target_evidence"]: store.validate_package_chunk(c)
        n=normalize_spec(spec)
        r=retriever.retrieve(n)
        g=gap_analysis(n,study,part,r,library)
        normalized.append(n)
        results.append({"identity":ident,**r})
        plans.append(g)
        for rank,c in enumerate(r["candidates"],1):
            rows.append({"tfl_id":ident["tfl_id"],"title":ident["title"],"rank":rank,
                         "template_id":c["template_id"],"preset_id":c["preset_id"],"score":c["score"],
                         **c["components"],"structural_conflict":c["structural_conflict"]})
    _write_json(out/"Normalized_Requirements.json",normalized)
    _write_json(out/"Template_Retrieval.json",results)
    _write_json(out/"Gap_Analysis.json",plans)
    _write_csv(out/"Candidate_Rankings.csv",rows,["tfl_id","title","rank","template_id","preset_id","score",
                                                "keyword","semantic","structure","statistics","preset","structural_conflict"])
    report={"sap_sha256":hashes.pop(),"library":library.summary(),"llm_calls":0,
            "model":getattr(retriever.encoder,"model_name",type(retriever.encoder).__name__),
            "targets":[{"tfl_id":r["identity"]["tfl_id"],"baseline_template":r["baseline"]["template_id"],
                        "baseline_preset":r["baseline"]["preset_id"],"template":r["template_id"],"preset":r["preset_id"],
                        "status":r["status"],"flags":r["flags"],"top_score":r["candidates"][0]["score"] if r["candidates"] else None,
                        "gap_actions":len(g["actions"]),"coverage_review_count":len(g["coverage_review"])}
                       for r,g in zip(results,plans)],
            "clinical_confirmation":False,"generation_authorized":False,
            "evaluation_status":"Unlabelled pilot; no improvement or accuracy claim"}
    _write_json(out/"Summary.json",report)
    return report,results,plans
