"""Synthetic tests for Phase 6.4C; no network calls."""
from copy import deepcopy
import pytest
from tfl_agent.agent.phase6_specification_pilot import (
    supplement,validate_chunk,locate,audit_claims,specification,MAX_EXTRA_CHUNKS,MAX_EXTRA_CHARS)

def chunk(cid,text):
    return {"chunk_id":cid,"section":"1","pages":[1],"text":text,
            "source_spans":[{"block_id":cid,"page":1,"start":0,"end":len(text)}]}

def request():
    c=chunk("c1","Counts by category will be reported.")
    return {"request_id":"r","study_id":"s","entry_id":"e","sap_sha256":"hash",
            "source_chunks":[c],"payload":{"target":{"title":"Counts by category","output_type":"table"}}}

def claim(**kw):
    return {"field":"statistics","value":"Counts","source":"sap","chunk_id":"c1",
            "exact_quote":"Counts by category","applicability":"target_specific","reason":"Explicit counts.",
            **kw} if not kw else {**claim(),**kw}

def test_primary_never_replaced():
    base=[chunk("base","Primary evidence")]
    extra,audit=supplement(base,base+[chunk("other","Unrelated text"),chunk("new","General Statistical Methods")],[],{"title":"Counts"})
    assert [c["chunk_id"] for c in extra]==["new"]
    assert not any(r["chunk_id"]=="base" for r in audit)

def test_extra_budget():
    cs=[chunk(str(i),"General Statistical Methods "+("x"*1000)) for i in range(10)]
    extra,_=supplement([],cs,[],{"title":"Example"})
    assert len(extra)<=MAX_EXTRA_CHUNKS and sum(len(c["text"]) for c in extra)<=MAX_EXTRA_CHARS

def test_duplicate_mismatch_fails():
    with pytest.raises(ValueError): supplement([chunk("c","a")],[chunk("c","b")],[],{"title":"a"})

def test_spans_and_exact_location():
    c={"chunk_id":"c","text":"abc\ndef","pages":[1,2],"source_spans":[
       {"block_id":"a","page":1,"start":3,"end":6},{"block_id":"b","page":2,"start":8,"end":11}]}
    validate_chunk(c)
    assert locate(c,"bc\nde")==[{"block_id":"a","page":1,"start":4,"end":6},{"block_id":"b","page":2,"start":8,"end":10}]
    assert locate(c,"not present")==[]

def test_claim_candidate_and_unknown_fields():
    r=request();rows=audit_claims({"claims":[claim()]},r);s=specification(r,rows,"parsed")
    assert rows[0]["status"]=="evidence_backed_candidate"
    assert s["fields"]["statistics"]["values"]==["Counts"]
    assert s["fields"]["confidence_intervals"]["status"]=="unknown"
    assert not s["generation_authorized"] and not s["semantic_applicability_verified"]

@pytest.mark.parametrize("change",[
    {"chunk_id":"invented"},{"exact_quote":"invented"},{"value":"mean"},{"field":"unknown"},
    {"field":[]},{"reason":""},{"applicability":"confirmed"},
    {"source":"title","chunk_id":None,"field":"denominator"}])
def test_reject_invalid_claim(change):
    r=audit_claims({"claims":[claim(**change)]},request())[0]
    assert r["status"]=="rejected"

def test_uncertain_is_not_promoted():
    r=request();rows=audit_claims({"claims":[claim(applicability="uncertain")]},r)
    assert rows[0]["status"]=="needs_review"
    assert specification(r,rows,"parsed")["fields"]["statistics"]["status"]=="needs_review"

def test_duplicate_and_conflicting_applicability():
    rows=audit_claims({"claims":[claim(),claim(),claim(applicability="not_applicable")]},request())
    assert [r["status"] for r in rows]==["needs_review","duplicate","needs_review"]

def test_title_identity_separate_from_sap():
    rows=audit_claims({"claims":[claim(source="title",chunk_id=None)]},request())
    assert rows[0]["status"]=="title_explicit_candidate" and rows[0]["source_spans"]==[]

def test_empty_claims_allowed():
    r=request();rows=audit_claims({"claims":[]},r)
    assert len(specification(r,rows,"parsed")["unknown_fields"])==12

def test_missing_array_fails():
    with pytest.raises(ValueError): audit_claims({},request())
