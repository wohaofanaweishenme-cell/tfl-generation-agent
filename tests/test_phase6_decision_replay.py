"""Synthetic regression tests; no SAP, archive, credentials or LLM calls."""
from copy import deepcopy
import pytest
from tfl_agent.agent.phase6_decision_replay import replay_decision, summarize

@pytest.fixture
def example():
    payload={"target":{"title":"Summary of change from baseline","output_type":"table"},
             "library":{"templates":[{"template_id":"A","presets":[{"preset_id":"PA"}]},
                                      {"template_id":"B","presets":[{"preset_id":"PB"}]}]},
             "sap_evidence":[{"chunk_id":"c1","text":"Change from baseline will be summarized."}]}
    obj={"ranking":["A","B"],"selected_template":"A","selected_preset":"PA",
         "selection_status":"candidate_only","reason":"title",
         "candidate_assessments":[
             {"template_id":"A","compatibility":"supported","reason":"title",
              "missing_information":[],"citations":[{"source":"title","chunk_id":None,"exact_quote":"change from baseline"}]},
             {"template_id":"B","compatibility":"uncertain","reason":"unknown",
              "missing_information":["method"],"citations":[]}]}
    return obj,payload

def test_supported(example):
    obj,payload=example
    d=replay_decision(obj,payload)
    assert d["protocol_valid"] and d["supported_template"]=="A"
    assert d["supported_preset"]=="PA" and d["alternatives"]==["B"]
    assert not d["semantic_applicability_verified"] and not d["generation_authorized"]

def test_uncertain_nonnull(example):
    obj,payload=example
    obj["selection_status"]="uncertain"
    obj["candidate_assessments"][0]["compatibility"]="uncertain"
    d=replay_decision(obj,payload)
    assert d["protocol_valid"] and d["protocol_repaired"]
    assert d["recommended_template"]=="A" and d["supported_template"] is None
    assert d["supported_preset"] is None and d["uncertainty"]

def test_uncertain_null(example):
    obj,payload=example
    obj.update(selection_status="uncertain",selected_template=None,selected_preset=None)
    d=replay_decision(obj,payload)
    assert d["protocol_valid"] and not d["protocol_repaired"]
    assert d["recommended_template"]=="A" and d["supported_template"] is None

def test_no_compatible(example):
    obj,payload=example
    obj.update(selection_status="no_compatible_template",selected_template=None,selected_preset=None)
    d=replay_decision(obj,payload)
    assert d["protocol_valid"] and d["decision_status"]=="no_compatible_template"
    assert d["supported_template"] is None

@pytest.mark.parametrize("mutation,issue",[
    ("duplicate_rank","invalid_complete_ranking"),
    ("unknown_rank","invalid_complete_ranking"),
    ("malformed_rank","invalid_complete_ranking"),
    ("duplicate_assessment","invalid_or_duplicate_assessment_id"),
    ("bad_quote","invalid_exact_citation"),
    ("bad_chunk","invalid_exact_citation"),
    ("wrong_preset","invalid_preset_ownership"),
    ("wrong_selection","selection_not_rank_first"),
    ("bad_status","invalid_selection_status"),
    ("empty_citation","unsupported_candidate_only"),
])
def test_fail_closed(example,mutation,issue):
    obj,payload=example
    if mutation=="duplicate_rank": obj["ranking"]=["A","A"]
    elif mutation=="unknown_rank": obj["ranking"]=["A","C"]
    elif mutation=="malformed_rank": obj["ranking"]=["A",{}]
    elif mutation=="duplicate_assessment": obj["candidate_assessments"][1]=deepcopy(obj["candidate_assessments"][0])
    elif mutation=="bad_quote": obj["candidate_assessments"][0]["citations"][0]["exact_quote"]="fabricated"
    elif mutation=="bad_chunk": obj["candidate_assessments"][0]["citations"][0].update(source="sap",chunk_id="absent")
    elif mutation=="wrong_preset": obj["selected_preset"]="PB"
    elif mutation=="wrong_selection": obj["selected_template"]="B"
    elif mutation=="bad_status": obj["selection_status"]="confirmed"
    elif mutation=="empty_citation": obj["candidate_assessments"][0]["citations"]=[]
    d=replay_decision(obj,payload)
    assert issue in d["issues"]
    assert not d["protocol_valid"] and d["supported_template"] is None
    assert not d["generation_authorized"]

def test_bad_alternative_citation_blocks_support_not_ranking(example):
    obj,payload=example
    obj["candidate_assessments"][1]["citations"]=[{"source":"sap","chunk_id":"c1","exact_quote":"not present"}]
    d=replay_decision(obj,payload)
    assert d["ranking_valid"] and d["recommended_template"]=="A"
    assert not d["protocol_valid"] and d["supported_template"] is None

def test_exact_sap_citation_does_not_prove_applicability(example):
    obj,payload=example
    obj["candidate_assessments"][0]["citations"]=[{"source":"sap","chunk_id":"c1","exact_quote":"Change from baseline"}]
    d=replay_decision(obj,payload)
    assert d["protocol_valid"] and d["citation_audit"][0]["exact_match"]
    assert d["citation_audit"][0]["applicability"]=="unreviewed"

def test_uncertain_bad_citation_not_repaired(example):
    obj,payload=example
    obj["selection_status"]="uncertain"
    obj["candidate_assessments"][0]["citations"][0]["exact_quote"]="invented"
    d=replay_decision(obj,payload)
    assert not d["protocol_valid"] and not d["protocol_repaired"]
    assert d["supported_template"] is None
