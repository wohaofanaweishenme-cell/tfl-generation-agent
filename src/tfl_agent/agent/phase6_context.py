"""Phase 6.1: read-only, full-candidate context from approved Generic Library."""
from __future__ import annotations
from collections import Counter
from pathlib import Path
import json
from tfl_agent.tools.generic_library import load_generic_library

TYPES=("table","figure","listing")
def compact_json(obj):
    return json.dumps(obj,ensure_ascii=False,separators=(",",":"),sort_keys=True)
def write_json(path,obj):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

def make_context(library,kind):
    if kind not in TYPES: raise ValueError("Unknown output type")
    out=[]
    for tid in sorted(library.templates):
        t=library.template(tid)
        if t["output_type"]!=kind: continue
        d={k:t[k] for k in ("template_id","version","output_type","name","intended_use","not_for","structural_signature","required_fields","keywords","aliases","match_cues","config_options")}
        # Keep complete required-field constraints. Defaults are candidates, not target facts.
        d["presets"]=[]
        for pid in sorted(t["presets"]):
            p=library.preset(tid,pid)
            d["presets"].append({k:p[k] for k in ("preset_id","template_id","name","keywords","aliases","defaults","default_status")})
        out.append(d)
    if not out: raise ValueError("No eligible templates")
    expected={tid for tid,t in library.templates.items() if t["output_type"]==kind}
    pairs={(t["template_id"],p["preset_id"]) for t in out for p in t["presets"]}
    if {t["template_id"] for t in out}!=expected or pairs!={k for k in library.presets if k[0] in expected}:
        raise ValueError("Incomplete context")
    return {"output_type":kind,"templates":out,"policy":"All same-type templates and presets. Library defaults describe possible presentations, never target-study evidence. No source shells or gold labels in context. Do not infer missing clinical facts."}

def run_context(root,out):
    lib=load_generic_library(root)
    out=Path(out); out.mkdir(parents=True,exist_ok=False)
    contexts={k:make_context(lib,k) for k in TYPES}
    stats={}
    for k,c in contexts.items():
        compact=compact_json(c)
        stats[k]={"templates":len(c["templates"]),"presets":sum(len(t["presets"]) for t in c["templates"]),"characters":len(compact),"utf8_bytes":len(compact.encode("utf-8")),"whitespace_words":len(compact.split()),"llm_tokens":None}
        write_json(out/f"{k}_Context.json",c)
    s={"library":lib.summary(),"contexts":stats,"template_count":sum(x["templates"] for x in stats.values()),"preset_count":sum(x["presets"] for x in stats.values()),"new_llm_calls":0,"token_note":"Character/byte counts measured; exact LLM tokenizer count unavailable. No truncation."}
    if s["template_count"]!=len(lib.templates) or s["preset_count"]!=len(lib.presets): raise ValueError("Incomplete Library context")
    write_json(out/"Summary.json",s)
    return s
