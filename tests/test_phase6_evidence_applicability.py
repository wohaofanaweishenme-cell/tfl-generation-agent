"""Synthetic tests for evidence triage and the zero-call policy ablation."""
import pytest
from tfl_agent.agent.phase6_evidence_applicability import (
    triage, context_window, guarded_decision)


def decision(rec="A", supported="A", valid=True, status="supported_candidate"):
    return {"recommended_template":rec,"supported_template":supported,
            "protocol_valid":valid,"decision_status":status}


def test_agreement_preserves_existing_support():
    result=guarded_decision(decision(),decision())
    assert result["guarded_recommendation"]=="A"
    assert result["guarded_supported_template"]=="A"
    assert result["guarded_supported_preset"] is None
    assert not result["generation_authorized"]
    assert not result["semantic_applicability_verified"]


def test_sap_override_blocked_even_if_sap_is_supported():
    result=guarded_decision(decision(),decision("B","B"))
    assert result["guarded_recommendation"]=="A"
    assert result["guarded_supported_template"] is None
    assert result["decision_policy"]=="unverified_override_blocked"


def test_same_candidate_support_elevation_blocked():
    result=guarded_decision(decision(supported=None,status="uncertain"),decision())
    assert result["guarded_supported_template"] is None
    assert result["decision_policy"]=="unverified_support_elevation_blocked"


def test_sap_uncertainty_not_overwritten():
    result=guarded_decision(decision(),decision(supported=None,status="uncertain"))
    assert result["guarded_supported_template"] is None
    assert result["decision_policy"]=="uncertainty_preserved"


@pytest.mark.parametrize("status,valid", [("no_compatible_template",True),("invalid",False)])
def test_explicit_abstention_or_invalid_blocks_support(status,valid):
    result=guarded_decision(decision(),decision(supported=None,status=status,valid=valid))
    assert result["guarded_supported_template"] is None


def test_invalid_title_cannot_propose():
    result=guarded_decision(decision(valid=False,status="invalid"),decision())
    assert result["guarded_recommendation"] is None
    assert result["guarded_supported_template"] is None


def test_same_topic_is_not_semantic_proof():
    result=triage("Adverse Events","Adverse events are coded by SOC and PT.")
    assert "lexical_target_anchor" in result["triage_flags"]
    assert "possible_structural_or_statistical_cue" in result["triage_flags"]
    assert result["applicability_label"]=="unreviewed"
    assert result["discrimination_label"]=="unreviewed"


def test_general_context_hint():
    result=triage("Response at Week 6","Unless otherwise stated, percentages use non-missing data.")
    assert "possible_general_study_context" in result["triage_flags"]
    assert result["applicability_label"]=="unreviewed"


def test_title_evidence_not_sap():
    assert triage("Example","Example",source="title")["triage_flags"]==["title_evidence"]


def test_context_window_and_duplicate():
    result=context_window("abc quote xyz quote end","quote",radius=4)
    assert result["quote_start"]==4
    assert result["quote_occurrences"]==2
    assert result["context_before"]=="abc "
    assert result["context_after"]==" xyz"


def test_missing_and_malformed_quote():
    assert context_window("abc","absent")["quote_start"] is None
    assert context_window("abc",{})["quote_occurrences"]==0
    assert triage("Example",{})["applicability_label"]=="unreviewed"
