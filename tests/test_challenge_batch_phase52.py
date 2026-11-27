import pytest
from tfl_agent.agent.challenge_batch import select_cohort, validate_config

def test_cohort_keeps_failures_regressions_and_controls():
    rows=[]
    for i,(b,h) in enumerate([(False,False),(True,False),(True,True),(True,True),(True,True)]):
        for method,correct in (("title_rule",b),("title_keyword_dense_forced",h),("title_dense_forced",h)):
            rows.append({"study_id":"S","entry_id":str(i),"output_id":str(i),"output_type":"table",
                         "title":"T"+str(i),"expected":"A","outcome":"correct" if b else "wrong_template",
                         "method":method,"correct":str(correct)})
    cases=select_cohort(rows)
    assert len(cases)==4
    assert {c["stratum"] for c in cases}=={"baseline_failure","hybrid_regression","control"}
    assert cases==select_cohort(list(reversed(rows)))

def test_range_gate(tmp_path):
    import hashlib
    p=tmp_path/"library/studies/S/original/a.pdf"
    p.parent.mkdir(parents=True)
    p.write_bytes(b"pdf")
    original={"study_id":"S","pdf_path":str(p.relative_to(tmp_path)),"sha256":hashlib.sha256(b"pdf").hexdigest(),"max_body_page":8,"pdf_pages":20}
    cfg={**original,"body_verified":True,"api_authorized":True,"body_first":2,"body_last":8}
    assert validate_config(tmp_path,cfg,[original])[1]==(2,8)
    with pytest.raises(ValueError): validate_config(tmp_path,{**cfg,"body_last":9},[original])
    with pytest.raises(ValueError): validate_config(tmp_path,{**cfg,"api_authorized":False},[original])


def test_preferred_configs_bind_hash_and_do_not_approve():
    from tfl_agent.agent.challenge_batch import preferred_configs,PREFERRED_BODIES
    rows=[{"study_id":s,"sha256":h,"pdf_path":f"library/studies/{s}/original/a.pdf",
           "max_body_page":last+1,"pdf_pages":100} for s,(h,first,last) in PREFERRED_BODIES.items()]
    cfg=preferred_configs(rows)
    assert [(r["body_first"],r["body_last"]) for r in cfg]==[(10,30),(8,29),(5,27)]
    assert all(not r["body_verified"] and not r["api_authorized"] for r in cfg)
    with pytest.raises(ValueError): preferred_configs(rows[:-1])

def test_batch_retrieval_directory_and_subsets(tmp_path,monkeypatch):
    import tfl_agent.agent.challenge_batch as m
    cases=[{"study_id":"S","entry_id":str(i),"output_id":str(i),"title":"T"+str(i),
            "output_type":"table","expected":"A","outcome":"correct","stratum":"control"} for i in range(2)]
    mapping=[{**c,"registry_title_matches":True,"registry_type_matches":True,"relation":"direct_shell",
              "mapping_review_status":"verified","type_conflict":i==1} for i,c in enumerate(cases)]
    rows=[{**c,"method":name,"ranking":"A","selected":"A","selected_preset":""}
          for c in cases for name in ("title_rule","title_dense_forced","title_keyword_dense_forced")]
    monkeypatch.setattr(m,"validate_config",lambda *a:(tmp_path/"a.pdf",(2,3)))
    def retrieval(pdf,pages,targets,out,**kwargs):
        out.mkdir(parents=True)
        (out/"Evidence_Package.json").write_text("{}")
    def extraction(src,out,*a,**kwargs):
        assert src==out/"Retrieval"
        assert (src/"Evidence_Package.json").exists()
        return {"llm_calls":3},None,None
    def phase4(*a,**kwargs):
        return {},[{"identity":{"tfl_id":c["entry_id"]},"ablation_rankings":{"keyword_dense_no_structure":["A"]},
                    "candidates":[{"template_id":"A","structural_conflict":False}],
                    "template_id":"A","preset_id":None} for c in cases],None
    monkeypatch.setattr(m,"run_scope_retrieval",retrieval)
    monkeypatch.setattr(m,"run_specification_extraction",extraction)
    monkeypatch.setattr(m,"run_phase4",phase4)
    report=m.run_batch(tmp_path,cases,rows,[],mapping,[{"study_id":"S","body_verified":True,"api_authorized":True}],
                       tmp_path/"out",llm=object(),encoder=object())
    assert report["completed"]==2
    assert report["paired_completed_metrics"]["sap_aware"]["n"]==2
    assert report["paired_type_consistent_metrics"]["sap_aware"]["n"]==1
    assert report["paired_type_conflict_metrics"]["sap_aware"]["n"]==1
