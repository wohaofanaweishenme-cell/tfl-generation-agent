import pytest
from tfl_agent.agent.phase6_template_alignment import align,signals

def template(tid,s2,s4):
    return {"template_id":tid,"structural_signature":{"S1":"table","S2":s2,"S3":["GROUPS"],"S4":s4,"S5":["NONE"]},"not_for":""}

T=[template("variable","VAR_BLOCKS",["DESC","DESC_MIXED","SUBJ_N_PCT"]),
   template("rate","ENDPOINT_ANALYSIS",["RATE_CI"]),
   template("coded","CODED_HIERARCHY",["SUBJ_AND_EVENTS","SUBJ_N_PCT"]),
   template("criterion","CATEGORY_LIST",["SUBJ_AND_EVENTS","SUBJ_N_PCT"])]

def claim(field,value,i,source="sap",applicability="target_specific"):
    return {"field":field,"value":value,"claim_index":i,"source":source,"applicability":applicability}

def test_explicit_categories_not_missing_ci_drive_revision():
    c=[claim("endpoint","Complete (CR), Partial (PR), Stable (SD), Progressive (PD)",0),
       claim("statistics","number and percentage of participants",1)]
    d=align(T,"rate",c)
    assert d["recommended_template"]=="variable"
    assert d["decision"]=="provisional_revision"
    assert not d["generation_authorized"] and d["confirmed_template"] is None
    assert not any(s["signal"]=="response_rate_with_ci" for s in d["signals"])

def test_missing_evidence_never_negative():
    d=align(T,"rate",[])
    assert d["recommended_template"]=="rate" and d["decision"]=="insufficient_discriminating_shape"
    assert all(not m["tension_signals"] for m in d["matrix"])

def test_conflicting_row_shapes_do_not_override():
    c=[claim("row_requirements","by SOC and PT",0),claim("row_requirements","Deaths",1)]
    d=align(T,"criterion",c)
    assert d["recommended_template"]=="criterion" and d["decision"]=="conflicting_shape_evidence"

def test_coded_title_signal_is_candidate_only():
    d=align(T,"coded",[claim("row_requirements","by System Organ Class and Preferred Term",0,"title")])
    assert d["decision"]=="structure_supported_candidate" and d["confirmed_template"] is None

def test_general_ci_not_a_display_requirement():
    c=[claim("confidence_intervals","95% CI",0,applicability="explicitly_applicable_study_rule"),
       claim("statistics","response rate",1)]
    assert not any(s["signal"]=="response_rate_with_ci" for s in signals(c))

def test_statistics_alone_do_not_override():
    d=align(T,"variable",[claim("statistics","number of cases and number of events",0)])
    assert d["recommended_template"]=="variable" and d["decision"]=="insufficient_discriminating_shape"

def test_shape_statistic_tension_blocks_revision():
    c=[claim("row_requirements","by SOC and PT",0),
       claim("statistics","arithmetic mean and standard deviation",1)]
    d=align(T,"criterion",c)
    assert d["recommended_template"]=="criterion" and d["decision"]=="shape_statistic_tension"

def test_same_shape_multiple_candidates_abstain():
    t=T+[template("another_coded","CODED_HIERARCHY",["SUBJ_N_PCT"])]
    d=align(t,"criterion",[claim("row_requirements","by SOC and PT",0)])
    assert d["recommended_template"]=="criterion" and d["decision"]=="multiple_shape_candidates"
