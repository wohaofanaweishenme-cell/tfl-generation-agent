"""Synthetic evidence and real approved library, deterministic test encoder."""
from pathlib import Path
import numpy as np
from tfl_agent.agent.requirement_normalizer import normalize_spec, enumeration_review
from tfl_agent.agent.sap_aware_retriever import SAPAwareRetriever, gap_analysis
from tfl_agent.tools.generic_library import load_generic_library

ROOT=Path(__file__).resolve().parents[1]

class Encoder:
    model_name="fake-test-only"
    def encode(self,texts,*,is_query=False):
        return np.array([[1+t.lower().count(w) for w in ("survival","demographic","kaplan","baseline","event","variable")] for t in texts])


def claim(field,value):
    return {"field":field,"value":value,"chunk_id":"test","source_spans":[],
            "status":"evidence_backed_candidate"}


def spec(title,claims,topic=None):
    return {"identity":{"tfl_id":"test","title":title,"output_type":"table"},"topic":topic,"claims":claims}


def test_normalize_and_coverage():
    n=normalize_spec(spec("Demographic and Baseline Characteristics",[
        claim("statistics_to_display","n, mean, Standard Deviation, median, minimum, maximum"),
        claim("variables_to_display","gender"),claim("column_requirements","by treatment groups")]))
    assert set(n["statistics"])=={"n","mean","sd","median","min","max"}
    assert set(n["variables"])=={"sex"}
    assert n["reporting_dimensions"][0]["value"]=="by treatment groups"
    missing=enumeration_review({"target_evidence":[{"chunk_id":"x","text":"Demographic characteristics will include gender, age, race, etc."}]},n)
    assert {x["value"] for x in missing}=={"age","race"}


def test_demographic_preset_gap():
    lib=load_generic_library(ROOT/"generic_template_library")
    n=normalize_spec(spec("Demographic and Baseline Characteristics",[
        claim("analysis_methods","descriptive statistics"),claim("statistics_to_display","n mean SD median minimum maximum frequencies percentages"),
        claim("variables_to_display","gender"),claim("variables_to_display","age")],"demographics"))
    r=SAPAwareRetriever(lib,Encoder()).retrieve(n)
    assert r["best_candidate_template_id"]=="TBL_VARIABLE_SUMMARY"
    assert r["best_candidate_preset_id"]=="demographics"
    # Explicit selection is tested independently of the provisional margin.
    g=gap_analysis(n,{"values":{}},{},dict(r,template_id="TBL_VARIABLE_SUMMARY",preset_id="demographics"),lib)
    assert any(a["action"]=="keep" and a.get("value")=="sex" for a in g["actions"])
    assert any(a["action"]=="review" and a.get("value")=="Weight" for a in g["actions"])
    assert not g["generation_authorized"]


def test_tte_strong_scope_and_gaps():
    lib=load_generic_library(ROOT/"generic_template_library")
    n=normalize_spec(spec("Summary of Progression Free Survival",[
        claim("analysis_methods","Kaplan-Meier methodology"),claim("endpoint_definition","time from first dose to progression"),
        claim("censoring_rules","censored at last assessment"),claim("statistics_to_display","Q1 median Q3 and 95% CI"),
        claim("statistics_to_display","number and % censored further divided by reasons for censoring")],"pfs"))
    r=SAPAwareRetriever(lib,Encoder()).retrieve(n)
    assert r["template_id"]=="TBL_TIME_TO_EVENT"
    assert r["preset_id"]=="event_time_summary"
    assert all(c["structural_conflict"] for c in r["candidates"] if c["template_id"]!="TBL_TIME_TO_EVENT")
    g=gap_analysis(n,{"values":{}},{},r,lib)
    assert any(a["element"]=="endpoint_row_detail" for a in g["actions"])
    assert not any(a["action"]=="add_candidate" and a.get("value") in {"q1","q3","ci"} for a in g["actions"])


def test_nonstandard_and_type_conflict():
    lib=load_generic_library(ROOT/"generic_template_library")
    for title in ("Listing of adverse events","Preface to Inclusion and Exclusion Criteria"):
        n=normalize_spec(spec(title,[claim("statistics_to_display","n")]))
        r=SAPAwareRetriever(lib,Encoder()).retrieve(n)
        assert r["template_id"] is None
        assert not r["generation_authorized"]


def test_confidence_level_is_not_categorical_percentage():
    n=normalize_spec(spec("PFS", [claim("statistics_to_display","Median and 95% CI")]))
    assert set(n["statistics"])=={"median","ci"}
    n=normalize_spec(spec("PFS", [claim("statistics_to_display","Median, 95% CI and number and % censored")]))
    assert set(n["statistics"])=={"median","ci","n","percentage"}


def test_total_column_not_inferred_from_groups():
    lib=load_generic_library(ROOT/"generic_template_library")
    n=normalize_spec(spec("PFS",[claim("column_requirements","each treatment group")]))
    g=gap_analysis(n,{"values":{}},{},{"template_id":"TBL_TIME_TO_EVENT","preset_id":"event_time_summary"},lib)
    assert any(a["element"]=="columns.total" and a["action"]=="review" for a in g["actions"])
