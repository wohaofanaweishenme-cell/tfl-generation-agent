import pytest
from tfl_agent.agent.scoped_specification import (
    EvidenceStore, verify_claims, extract_scope, target_evidence, STUDY_FIELDS,
)


def evidence():
    texts = ["The Q1, median and Q3 PFS time will be provided.",
             "Kaplan-Meier curves will be produced.",
             "The median duration of response will be provided.",
             "Group 1 receives 800 mg BID.",
             "All patients in the Safety analysis Set.",
             "ITT Analysis Set and PP Analysis Set."]
    topics = ["pfs","pfs","dor",None,"demographics","pfs"]
    studies = [None,None,None,"treatment_groups",None,None]
    blocks = [{"block_id":f"b{i}","page":i+1,"text":t} for i,t in enumerate(texts)]
    chunks = [{"chunk_id":f"c{i}","text":t,"section":"8.7","topic_scope":topics[i],
               "study_scope":studies[i],"source_spans":[{"block_id":f"b{i}","page":i+1,"start":0,"end":len(t)}]}
              for i,t in enumerate(texts)]
    store = EvidenceStore(blocks,chunks)
    pool = {c["chunk_id"]:{**c,"pool":"target_scoped"} for c in chunks}
    return store,pool


def claim(field,value,cid,quote,scope="table"):
    return {"field":field,"value":value,"chunk_id":cid,"quote":quote,
            "output_scope":scope,"applicability_reason":"Explicitly described for requested output."}


def test_quote_scope_and_population():
    store,pool = evidence()
    raw = {"claims":[
        claim("statistics_to_display","median","c0","median and Q3 PFS time"),
        claim("statistics_to_display","Q4","c0","median and Q3 PFS time"),
        claim("statistics_to_display","median","c0","invented median"),
        claim("statistics_to_display","median","c2","median duration of response"),
        claim("analysis_methods","Kaplan-Meier","c1","Kaplan-Meier curves will be produced."),
        claim("analysis_population","PP Analysis Set","c5","ITT Analysis Set and PP Analysis Set."),
    ]}
    a,r,x = verify_claims(raw,("statistics_to_display","analysis_methods","analysis_population"),
                          pool,store,target={"title":"PFS – ITT Analysis Set"},topic="pfs")
    assert len(a)==1 and len(r)==3 and len(x)==2
    assert a[0]["source_spans"][0]["start"] == store.blocks["b0"]["text"].index("median")
    assert all(not c["clinical_confirmation"] for c in a+r)


def test_study_and_tampered_evidence():
    store,pool=evidence()
    raw={"claims":[claim("treatment_groups","800 mg BID","c3","Group 1 receives 800 mg BID.","study")]}
    a,r,x=verify_claims(raw,STUDY_FIELDS,pool,store)
    assert len(a)==1 and not r and not x
    bad={**store.chunks["c0"],"text":"tampered"}
    with pytest.raises(ValueError,match="mismatch"):
        target_evidence({"pool":"target_scoped","target_evidence":[bad],"context_evidence":[]},store)


def test_unknown_context_cannot_become_verified():
    store,pool=evidence()
    pool["c0"]["pool"]="unclassified_context"
    a,r,x=verify_claims({"claims":[claim("statistics_to_display","median","c0","median and Q3 PFS time")]},
                        ("statistics_to_display",),pool,store,target={"title":"PFS"},topic="pfs")
    assert not a and len(r)==1 and not x


def test_completion_only_fills_missing_fields():
    store,pool=evidence()
    class Fake:
        def __init__(self):self.calls=0
        def json(self,system,user):
            self.calls+=1
            if self.calls==1:return {"claims":[claim("statistics_to_display","median","c0","median and Q3 PFS time")]}
            return {"claims":[claim("statistics_to_display","Q3","c0","median and Q3 PFS time"),
                              claim("analysis_population","ITT Analysis Set","c5","ITT Analysis Set and PP Analysis Set.")]}
    class Retriever:
        def retrieve(self,missing,**kwargs):
            assert missing==["analysis_population"]
            return {"c5":pool["c5"]},[]
    llm=Fake()
    result,audit=extract_scope(llm,{"c0":pool["c0"]},store,
                               ("statistics_to_display","analysis_population"),
                               ("statistics_to_display","analysis_population"),
                               target={"title":"PFS – ITT Analysis Set"},topic="pfs",completion=Retriever())
    assert llm.calls==2 and audit["recovered_fields"]==["analysis_population"]
    assert result["values"]["statistics_to_display"]==["median"]
    assert result["generation_authorized"] is False
    assert len(audit["rejected_claims"])==1


def test_multispan_quote_offsets():
    blocks=[{"block_id":"a","page":1,"text":"prefix alpha"},{"block_id":"b","page":2,"text":"beta suffix"}]
    chunks=[{"chunk_id":"c","text":"alpha\nbeta","source_spans":[
        {"block_id":"a","page":1,"start":7,"end":12},{"block_id":"b","page":2,"start":0,"end":4}]}]
    store=EvidenceStore(blocks,chunks)
    assert store.locate("c","alpha\nbeta")==chunks[0]["source_spans"]
    assert store.locate("c","alpha beta")==[]
