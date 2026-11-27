import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from tfl_agent.agent import unified_pipeline as u

def request(text="test"):
    return u.make_request("matching", {"text":text}, "test system")

def test_cache_miss_never_calls_api(monkeypatch):
    monkeypatch.setattr(u,"preflight_deepseek",lambda *a,**k: pytest.fail("Unexpected API preflight"))
    e=u.ResponseExecutor()
    assert e.get(request())["status"]=="not_attempted"
    assert e.new_attempts==0

def test_exact_cache_and_tampering():
    r=request()
    e=u.ResponseExecutor(frozen={r["fingerprint"]:{"fingerprint":r["fingerprint"],"raw_response":"{}","finish_reason":"stop"}})
    assert e.get(r)["cache_source"]=="verified_frozen_archive"
    assert e.get(request("different"))["status"]=="not_attempted"
    r["config"]["payload"]["text"]="modified"
    with pytest.raises(ValueError): e.get(r)

def test_budget_requires_authorization(tmp_path):
    with pytest.raises(ValueError): u.ResponseExecutor(tmp_path,max_new_attempts=1)
    with pytest.raises(ValueError): u.ResponseExecutor(authorized=True,max_new_attempts=1)

def test_preflight_stops_without_reservation(tmp_path,monkeypatch):
    def fail(*args,**kwargs): raise RuntimeError("test")
    monkeypatch.setattr(u,"preflight_deepseek",fail)
    e=u.ResponseExecutor(tmp_path,authorized=True,max_new_attempts=2,api_key="dummy")
    assert e.get(request())["status"]=="preflight_failed"
    assert e.get(request("second"))["status"]=="not_attempted"
    assert not list(tmp_path.glob("*.attempt.json"))

def test_api_failure_is_not_retried(tmp_path,monkeypatch):
    calls=[]
    def fail(**kw):
        calls.append(kw)
        raise RuntimeError("test")
    monkeypatch.setattr(u,"preflight_deepseek",lambda *a,**k:SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fail))))
    e=u.ResponseExecutor(tmp_path,authorized=True,max_new_attempts=2,api_key="dummy")
    assert e.get(request())["status"]=="api_failed"
    assert e.get(request("second"))["status"]=="not_attempted"
    assert e.get(request())["cache_source"]=="persistent_cache"
    assert len(calls)==1
    e2=u.ResponseExecutor(tmp_path,authorized=True,max_new_attempts=2,api_key="dummy")
    assert e2.get(request())["cache_source"]=="persistent_cache"
    assert len(calls)==1

def test_reserved_unknown_never_retried(tmp_path,monkeypatch):
    r=request()
    e=u.ResponseExecutor(tmp_path,authorized=True,max_new_attempts=1,api_key="dummy")
    u.write_json(tmp_path/(r["fingerprint"]+".attempt.json"),{"fingerprint":r["fingerprint"]})
    monkeypatch.setattr(u,"preflight_deepseek",lambda *a,**k:pytest.fail("Unexpected request"))
    assert e.get(r)["status"]=="reserved_unknown"
    assert e.get(request("different"))["status"]=="not_attempted"
    with pytest.raises(ValueError): u.ResponseExecutor(tmp_path,authorized=True,max_new_attempts=2)

def test_parse_old_failed_protocol_response():
    obj,status=u.parse_record({"status":"failed","finish_reason":"stop","raw_response":"{}"})
    assert obj=={} and status=="parsed"
    assert u.parse_record({"finish_reason":"length","raw_response":"{}"})[0] is None

def test_pdf_dry_run_and_mocked_downstream(tmp_path):
    import fitz
    import numpy as np
    class Encoder:
        model_name="synthetic-test-encoder"
        def encode(self,texts,is_query=False):
            return np.array([[1.,float("deviation" in t.lower()),float("safety" in t.lower())] for t in texts])
    doc=fitz.open()
    page=doc.new_page()
    page.insert_text((72,72),"6.3 Protocol Deviations")
    page.insert_text((72,100),"All protocol deviations in each arm will be summarized by severity and categories.")
    page=doc.new_page()
    page.insert_text((72,72),"REFERENCE SHELL ONLY NEVER RETRIEVE")
    path=tmp_path/"test.pdf";doc.save(path);doc.close()
    root=Path(__file__).resolve().parents[1]/"generic_template_library"
    agent=u.TFLAgent(root,encoder=Encoder())
    plan=agent.prepare(path,"Summary of Protocol Deviation",body_pages=(1,1))
    assert plan["retrieval"]["body_pages"]==[1,1]
    assert plan["source_chunks"] and all(c["pages"]==[1] for c in plan["source_chunks"])
    assert all("REFERENCE SHELL" not in c["text"] for c in plan["source_chunks"])
    assert set(plan["specification_request"]["config"]["payload"])=={"target","sap_evidence","allowed_fields"}
    dry=u.finish_prepared(plan,u.ResponseExecutor())
    assert dry["new_attempts"]==0 and not dry["complete_candidate_pipeline"]
    assert dry["recommended_template"] is None
    mp=plan["matching_request"]["config"]["payload"]
    tid=mp["library"]["templates"][0]["template_id"]
    match={"ranking":[tid],"recommended_template":tid,"supported_template":None,
           "selection_status":"uncertain","proposed_preset":None,"reason":"test only",
           "candidate_assessments":[{"template_id":tid,"compatibility":"uncertain","reason":"test","missing_information":[],"citations":[]}]}
    spec={"claims":[{"field":"endpoint","value":"Protocol Deviation","source":"title","chunk_id":None,
                     "exact_quote":"Protocol Deviation","applicability":"target_specific","reason":"Explicit in title"}]}
    frozen={}
    for key,obj in (("matching_request",match),("specification_request",spec)):
        fp=plan[key]["fingerprint"]
        frozen[fp]={"fingerprint":fp,"raw_response":json.dumps(obj),"finish_reason":"stop","status":"response_received"}
    final=u.finish_prepared(plan,u.ResponseExecutor(frozen=frozen))
    assert final["complete_candidate_pipeline"] and final["matching_protocol_valid"]
    assert final["recommended_template"]==tid and len(final["claim_audit"])==1
    assert final["confirmed_template"] is None and not final["generation_authorized"]
    assert final["new_attempts"]==0
