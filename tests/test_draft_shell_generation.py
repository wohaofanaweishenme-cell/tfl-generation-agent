"""Offline schema and native Word integration checks for all nine table families."""
from pathlib import Path
import copy
import pytest
from docx import Document
from tfl_agent.tools.generic_library import load_generic_library
from tfl_agent.agent.draft_shell_generation import (
    FAMILIES, build_draft_spec, generate_editable_draft, statistic_kind
)

@pytest.fixture(scope="module")
def library():
    return load_generic_library(Path(__file__).resolve().parents[1]/"generic_template_library")

def fixture(tid, title="Demographic and Baseline Characteristics – Safety Analysis Set"):
    text="Group A; mean; Age; unrelated secret category"
    def claim(i, field, val, route="unverified_candidate"):
        return {"claim_index":i,"field":field,"value":val,"source":"sap",
                "chunk_id":"c1","exact_quote":val,"exact_match":True,"literal_support":True,
                "source_spans":[{"page":4,"block_id":"b1","start":text.index(val),"end":text.index(val)+len(val)}],
                "rule_route":route}
    return {"complete_candidate_pipeline":True,"recommended_template":tid,
            "proposed_preset":None,"generation_authorized":False,"confirmed_template":None,
            "matching_protocol_valid":True,"matching":{"rank_prefix":[tid]},
            "entry_id":"14.1.3.1","target":{"title":title,"output_type":"table"},
            "sap_sha256":"a"*64,"source_chunks":[{"chunk_id":"c1","text":text}],
            "claim_audit":[claim(0,"treatment_groups","Group A"),claim(1,"statistics","mean"),
                           claim(2,"row_requirements","Age"),
                           claim(3,"row_requirements","unrelated secret category","needs_review")]}

@pytest.mark.parametrize("tid",sorted(FAMILIES))
def test_render_all_table_families(tmp_path,library,tid):
    original=copy.deepcopy(library.style)
    result=fixture(tid)
    info=generate_editable_draft(result,library,tmp_path/tid)
    assert info["schema_valid"] and info["native_word_tables"]>=1
    assert not info["generation_authorized"] and info["new_llm_calls"]==0
    assert library.style==original
    doc=Document(tmp_path/tid/info["file"])
    text=" ".join([p.text for p in doc.paragraphs]+[c.text for t in doc.tables for r in t.rows for c in r.cells])
    assert result["target"]["title"] in text
    assert "unrelated secret category" not in text
    assert "DRAFT - NOT CLINICALLY VALIDATED" in text
    assert "Group A" in text
    assert doc.sections[0].header.paragraphs[0].text.startswith("DRAFT")

def test_candidate_population_and_exact_statistic(library):
    result=fixture("TBL_VARIABLE_SUMMARY")
    spec,audit,style=build_draft_spec(result,library)
    assert spec["population"]["value"]=="Safety Analysis Set"
    assert spec["columns"]["groups"][0]["label"]["value"]=="Group A"
    assert spec["columns"]["total"]["enabled"]["status"]=="unresolved"
    assert statistic_kind("n (%)",style)=="n_pct"
    assert 3 not in [c["claim_index"] for c in audit["source_claims"]]
    assert spec["title"]["value"]==result["target"]["title"]

def test_incomplete_agent_cannot_render(tmp_path,library):
    r=fixture("TBL_VARIABLE_SUMMARY")
    r["complete_candidate_pipeline"]=False
    with pytest.raises(ValueError,match="complete candidate"):
        generate_editable_draft(r,library,tmp_path)
    assert not list(tmp_path.glob("*.docx"))
