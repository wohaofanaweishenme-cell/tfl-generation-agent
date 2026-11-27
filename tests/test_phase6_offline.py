from pathlib import Path
from tfl_agent.tools.generic_library import load_generic_library
from tfl_agent.agent.phase6_context import make_context
from tfl_agent.agent.phase6_retrieval import soft_rank,round_robin,topic_for

def test_library_context():
    root=Path(__file__).resolve().parents[1]/"generic_template_library"
    lib=load_generic_library(root)
    cs=[make_context(lib,k) for k in ("table","figure","listing")]
    assert sum(len(c["templates"]) for c in cs)==16
    assert sum(len(t["presets"]) for c in cs for t in c["templates"])==66
    assert all("evidence" not in t and "evidence" not in p for c in cs for t in c["templates"] for p in t["presets"])
def test_soft_scope_never_drops():
    chunks={"a":{"topic_scope":"ae","study_scope":None},"b":{"topic_scope":"protocol_deviations","study_scope":None},"c":{"topic_scope":None,"study_scope":None}}
    hits=[{"chunk_id":i,"rank":j,"score":.02} for j,i in enumerate(chunks,1)]
    assert [h["chunk_id"] for h in soft_rank(hits,chunks,"protocol_deviations")]==["b","c","a"]
    assert [h["chunk_id"] for h in soft_rank(hits,chunks,None)]==["a","b","c"]
def test_protocol_singular():
    assert topic_for("Summary of Protocol Deviation")=="protocol_deviations"
def test_round_robin():
    assert round_robin([[{"chunk_id":"a"},{"chunk_id":"b"}],[{"chunk_id":"a"},{"chunk_id":"c"}]])==["a","b","c"]
