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
