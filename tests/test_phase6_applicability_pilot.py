"""Synthetic tests for the revised prompt contract; no API calls."""
from copy import deepcopy
import pytest
from tfl_agent.agent.phase6_applicability_pilot import validate

@pytest.fixture
def example():
    payload={"target":{"title":"Counts by category","output_type":"table"},
             "library":{"templates":[{"template_id":"A","presets":[{"preset_id":"PA"}]},
                                      {"template_id":"B","presets":[{"preset_id":"PB"}]}]},
             "sap_evidence":[{"chunk_id":"c1","text":"Counts by category will be reported."}]}
    c={"source":"sap","chunk_id":"c1","exact_quote":"Counts by category",
       "applicability":"target_specific","discrimination":"supports_candidate_over_alternative",
       "competing_template":"B","use":"structural_support","reason":"Explicit categories."}
    obj={"target_interpretation":{"object_endpoint":"counts","timepoint":"unknown","population":"unknown","output_type":"table"},
         "title_hypothesis":"A","passage_review":[{"chunk_id":"c1","disposition":"potentially_relevant","reason":"counts"}],
         "ranking":["A","B"],"recommended_template":"A","supported_template":"A","proposed_preset":"PA",
         "selection_status":"candidate_only","reason":"categories",
         "candidate_assessments":[{"template_id":"A","compatibility":"supported","reason":"counts","citations":[c],"missing_information":[]},
                                  {"template_id":"B","compatibility":"uncertain","reason":"unknown","citations":[],"missing_information":[]}]}
    return obj,payload

def test_valid(example):
    obj,p=example
    d=validate(obj,p)
    assert d["supported_template"]=="A"
    assert d["supported_preset"] is None
    assert not d["semantic_applicability_verified"] and not d["generation_authorized"]

def test_uncertain(example):
    obj,p=example
    obj.update(supported_template=None,selection_status="uncertain")
    obj["candidate_assessments"][0]["compatibility"]="uncertain"
    assert validate(obj,p)["supported_template"] is None

def test_no_compatible(example):
    obj,p=example
    obj.update(recommended_template=None,supported_template=None,proposed_preset=None,selection_status="no_compatible_template")
    obj["candidate_assessments"][0]["compatibility"]="uncertain"
    assert validate(obj,p)["recommended_template"] is None

@pytest.mark.parametrize("mutation",["other_endpoint","general_context","bad_quote","no_review","bad_preset","uncertain_supported","bad_competitor","context_only","unknown_title","unsupported_override"])
def test_fail_closed(example,mutation):
    obj,p=example
    c=obj["candidate_assessments"][0]["citations"][0]
    if mutation=="other_endpoint": c["applicability"]="other_endpoint_or_output"
    elif mutation=="general_context": c["applicability"]="general_study_context"
    elif mutation=="bad_quote": c["exact_quote"]="invented"
    elif mutation=="no_review": obj["passage_review"]=[]
    elif mutation=="bad_preset": obj["proposed_preset"]="PB"
    elif mutation=="uncertain_supported": obj["selection_status"]="uncertain"
    elif mutation=="bad_competitor": c["competing_template"]="A"
    elif mutation=="context_only": c["use"]="context"
    elif mutation=="unknown_title": obj["title_hypothesis"]="X"
    elif mutation=="unsupported_override":
        obj["title_hypothesis"]="B"
        c.update(source="title",chunk_id=None,applicability="title_explicit")
    with pytest.raises(ValueError): validate(obj,p)

def test_applicable_discriminating_override(example):
    obj,p=example
    obj["title_hypothesis"]="B"
    assert validate(obj,p)["supported_template"]=="A"
