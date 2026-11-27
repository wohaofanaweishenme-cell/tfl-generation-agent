"""Synthetic Phase 6.4B tests; no encoder download, clinical data or LLM."""
import pytest
from tfl_agent.agent.phase6_field_retrieval import (
    GROUPS, FIELDS, query_plan, rank_groups, allocate, historical_overlap)

def test_all_fields_and_queries():
    plans=query_plan({"title":"Summary of Response","output_type":"table"})
    assert len(plans)==10
    assert set(f for p in plans for f in p["fields"])==set(FIELDS)
    assert all("Summary of Response" in p["query"] for p in plans if p["query_scope"]=="target")
    assert all("Summary of Response" not in p["query"] for p in plans if p["query_scope"]=="context")

def results():
    return [{**p,"methods":{"hybrid":[{"chunk_id":"shared","rank":1},{"chunk_id":p["group"],"rank":2}]}}
            for p in query_plan({"title":"Example"})]

def test_group_fusion_and_dedup():
    ranked,hits=rank_groups(results())
    assert len(hits["shared"])==10
    assert all(r[0]=="shared" for r in ranked.values())
    records={cid:{"text":"abc"} for cid in hits}
    picked,allocation=allocate(ranked,records,6)
    assert len(picked)==len(set(picked))==6
    assert sum(len(x) for x in allocation.values())==6

def test_budget_limits_without_truncation():
    ranked,hits=rank_groups(results())
    records={cid:{"text":"abc"} for cid in hits}
    ids,allocation=allocate(ranked,records,20,7)
    assert len(ids)==2
    assert sum(len(records[i]["text"]) for i in ids)<=7
    assert allocate(ranked,records,0)[0]==[]

def test_incomplete_query_results_rejected():
    with pytest.raises(ValueError): rank_groups(results()[:-1])

def test_duplicate_hit_rejected():
    r=results()
    r[0]["methods"]["hybrid"].append(r[0]["methods"]["hybrid"][0])
    with pytest.raises(ValueError): rank_groups(r)

def test_historical_overlap_not_gold():
    c={"field":"statistics_to_display","value":"counts","chunk_id":"c1","exact_quote":"counts by arm"}
    spec={"claims":[c,c],"review_claims":[c]}
    rows=historical_overlap(spec,{"c1":{"text":"counts by arm and group"},"c2":{"text":"counts by arm"}},{"baseline":["c1"],"expanded":["c2"]},{"request_id":"r"})
    assert len(rows)==1
    assert rows[0]["historical_statuses"]==["accepted","needs_review"]
    assert rows[0]["baseline_chunk_hit"] and rows[0]["expanded_quote_hit"]
    assert not rows[0]["expanded_chunk_hit"] and rows[0]["semantic_label"]=="unreviewed"

def test_historical_bad_provenance_fails():
    spec={"claims":[{"field":"statistics_to_display","value":"counts","chunk_id":"c1","exact_quote":"invented"}]}
    with pytest.raises(ValueError):
        historical_overlap(spec,{"c1":{"text":"counts"}},{"baseline":["c1"]},{})
