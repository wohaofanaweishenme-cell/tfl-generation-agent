import pytest
from tfl_agent.agent.phase6_llm_pilot import validate_response,decision_context,PILOT,BUDGET,ARMS
from tfl_agent.tools.generic_library import load_generic_library
from pathlib import Path
def fixture():
    p={"target":{"title":"AE overview","output_type":"table"},"library":{"templates":[{"template_id":"A","presets":[{"preset_id":"p"}]},{"template_id":"B","presets":[]}]},"sap_evidence":[]}
    obj={"ranking":["A","B"],"selected_template":"A","selected_preset":"p","selection_status":"candidate_only","reason":"title","candidate_assessments":[{"template_id":"A","compatibility":"supported","reason":"title","citations":[{"source":"title","chunk_id":None,"exact_quote":"AE overview"}],"missing_information":[]},{"template_id":"B","compatibility":"uncertain","reason":"not specified","citations":[],"missing_information":[]}]}
    return p,obj
def test_valid():
    p,o=fixture();assert validate_response(o,p)["generation_authorized"] is False
def test_wrong_quote():
    p,o=fixture();o["candidate_assessments"][0]["citations"][0]["exact_quote"]="not present"
    with pytest.raises(ValueError):validate_response(o,p)
def test_wrong_preset():
    p,o=fixture();o["selected_preset"]="bad"
    with pytest.raises(ValueError):validate_response(o,p)
def test_incomplete_ranking():
    p,o=fixture();o["ranking"]=["A"]
    with pytest.raises(ValueError):validate_response(o,p)
def test_abstention():
    p,o=fixture();o.update(selected_template=None,selected_preset=None,selection_status="uncertain")
    assert validate_response(o,p)["selected_template"] is None
def test_context():
    lib=load_generic_library(Path(__file__).resolve().parents[1]/"generic_template_library")
    c=decision_context(lib,"table")
    assert len(c["templates"])==9
    assert sum(len(t["presets"]) for t in c["templates"])==32
    assert len(PILOT)*len(ARMS)==BUDGET==18
