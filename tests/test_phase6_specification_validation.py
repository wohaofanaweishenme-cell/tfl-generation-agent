from types import SimpleNamespace
import pytest
from tfl_agent.agent.phase6_specification_validation import risk_flags,route,assemble
from tfl_agent.tools.deepseek_preflight import normalize_api_key,preflight_deepseek

def claim(**kw):
    return {"status":"evidence_backed_candidate","source":"sap","field":"statistics","value":"n (%)","exact_quote":"n (%)","applicability":"target_specific","claim_index":0,**kw}

def test_conditional_ci_is_not_display_requirement():
    r=claim(field="confidence_intervals",value="95% CI",exact_quote="Unless otherwise stated, 95% CI will be used.",applicability="explicitly_applicable_study_rule")
    flags=risk_flags(r)
    assert "ci_convention_not_display_requirement" in flags
    assert route(r,flags)=="scope_or_field_review"

def test_formatting_and_counting_method():
    for r in (claim(value="one decimal place",exact_quote="one decimal place"),claim(value="counted by PT")):
        assert route(r,risk_flags(r))=="scope_or_field_review"

def test_rejected_never_promoted():
    r=claim(status="rejected")
    assert route(r,risk_flags(r))=="rejected"

def test_vague_summary_not_statistic():
    r=claim(value="summarized")
    assert "unspecified_statistic" in risk_flags(r)

def test_multiple_values_not_automatic_conflict():
    req={"request_id":"r","study_id":"s","entry_id":"e","sap_sha256":"hash","payload":{"target":{"title":"Summary","output_type":"table"}}}
    rows=[claim(field="analysis_population",value="FAS",rule_route="unverified_candidate"),claim(field="analysis_population",value="SS",claim_index=1,rule_route="unverified_candidate")]
    s=assemble(req,rows,"rule_route",{"unverified_candidate"})
    assert s["fields"]["analysis_population"]["values"]==["FAS","SS"]
    assert s["fields"]["analysis_population"]["multiple_values_require_scope_check"]
    assert s["fields"]["confidence_intervals"]["requiredness"]=="undetermined"
    assert not s["generation_authorized"]

def test_key_normalization():
    assert normalize_api_key("  sk-example\n")=="sk-example"
    for key in ("",None,"sk- x"):
        with pytest.raises(ValueError): normalize_api_key(key)

def test_preflight_uses_stripped_key_without_generation():
    captured={}
    def factory(**kw):
        captured.update(kw)
        return SimpleNamespace(models=SimpleNamespace(list=lambda:SimpleNamespace(data=[SimpleNamespace(id="deepseek-flash")])))
    preflight_deepseek(" sk-example\n",client_factory=factory)
    assert captured["api_key"]=="sk-example" and captured["max_retries"]==0

def test_preflight_missing_model_stops():
    def factory(**kw):
        return SimpleNamespace(models=SimpleNamespace(list=lambda:SimpleNamespace(data=[])))
    with pytest.raises(RuntimeError): preflight_deepseek("sk-example",client_factory=factory)
