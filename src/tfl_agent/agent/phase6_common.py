"""Shared Phase 6 replay utilities. No LLM client."""
from __future__ import annotations
import csv,json,hashlib,zipfile
from pathlib import Path,PurePosixPath
from collections import defaultdict
from tfl_agent.agent.phase6_context import write_json

def read(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))
def read_csv(p):
    with Path(p).open(encoding="utf-8-sig",newline="") as f: return list(csv.DictReader(f))
def write_csv(p,rows,fields=None):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    fields=fields or list(dict.fromkeys(k for r in rows for k in r))
    with p.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def key(r):
    return r["study_id"],r["entry_id"]
def extract_phase52(archive,destination):
    dest=Path(destination);dest.mkdir(parents=True,exist_ok=False)
    with zipfile.ZipFile(archive) as z:
        for m in z.infolist():
            p=PurePosixPath(m.filename)
            if p.is_absolute() or ".." in p.parts or "\\" in m.filename: raise ValueError("Unsafe archive path")
        z.extractall(dest)
    roots=[p.parent for p in dest.rglob("Paired_Results.csv") if (p.parent/"Studies").is_dir() and (p.parent/"Summary.json").is_file()]
    if len(roots)!=1: raise ValueError("Select the single Phase52 run ZIP, not its parent folder")
    root=roots[0]; summary=read(root/"Summary.json")
    if summary["completed"]!=19 or summary["completed_phase3_llm_calls"]!=44:
        raise ValueError("Expected the 19-case / 44-recorded-call Phase 5.2 archive")
    return root

def cases(root):
    rs=[r for r in read_csv(root/"Paired_Results.csv") if r["method"]=="sap_aware"]
    done={key(r):r for r in read(root/"Case_Status.json") if r["status"]=="completed"}
    if len(rs)!=19 or len(done)!=19 or {key(r) for r in rs}!=set(done): raise ValueError("Case manifest mismatch")
    return [{**{f:r[f] for f in ("study_id","entry_id","output_id","title","output_type","expected","outcome","stratum")},"type_conflict":done[key(r)]["detail"]=="type_conflict_in_registry"} for r in rs]

def study_artifacts(root,study):
    from tfl_agent.agent.scoped_specification import EvidenceStore
    s=root/"Studies"/study; ret=s/"Retrieval"
    summary=read(ret/"Summary.json"); spec_summary=read(s/"Summary.json")
    configs=[c for c in read(root/"Run_Config.json") if c["study_id"]==study]
    if len(configs)!=1: raise ValueError("Missing original body configuration")
    c=configs[0]
    if not c["body_verified"] or summary["sap_sha256"]!=c["sha256"] or spec_summary["sap_sha256"]!=c["sha256"] or summary["physical_page_range"]!=[c["body_first"],c["body_last"]]:
        raise ValueError("SAP identity or body bounds mismatch")
    blocks=read(ret/"SAP_Blocks.json"); chunks=read(ret/"Scoped_Chunks.json")
    if any(not c["body_first"]<=b["page"]<=c["body_last"] for b in blocks):
        raise ValueError("Block outside verified body")
    store=EvidenceStore(blocks,chunks)
    pack=read(ret/"Evidence_Package.json")
    parts={p["target"]["tfl_id"]:p for p in pack["targets"]}
    specs=read(s/"TFL_Requirements.json")
    reqs={p["identity"]["tfl_id"]:p for p in specs}
    if len(parts)!=len(pack["targets"]) or len(reqs)!=len(specs) or set(parts)!=set(reqs):
        raise ValueError("Target identity mismatch")
    for p in parts.values():
        for field in ("target_evidence","context_evidence"):
            for ev in p[field]: store.validate_package_chunk(ev)
    for r in specs:
        if r["sap_sha256"]!=summary["sap_sha256"]: raise ValueError("Specification hash mismatch")
    return store,chunks,parts,reqs,summary

def verify_identity(case,part,spec):
    ident={"tfl_id":case["entry_id"],"title":case["title"],"output_type":case["output_type"]}
    for r in (part["target"],spec["identity"]):
        if any(r[k]!=v for k,v in ident.items()): raise ValueError("Case/artifact identity mismatch")
    return ident
