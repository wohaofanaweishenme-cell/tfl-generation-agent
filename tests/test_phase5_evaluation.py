from tfl_agent.agent.phase5_evaluation import row,metrics,aggregate,paired_case

def test_metrics_separate_abstention_and_ranking():
    cases=[{"expected":"A"},{"expected":"B"},{"expected":"NONSTANDARD"}]
    rows=[row("m",cases[0],["A","B"],"A"),row("m",cases[1],["A","B"],None),row("m",cases[2],["A"],None)]
    m=metrics(rows)
    assert m["selection_accuracy"]==2/3
    assert m["coverage"]==1/3
    assert m["recall_at_3"]==1
    assert m["mrr"]==.75
    assert m["nonstandard_abstention"]==1

def test_multi_label_and_no_labels():
    assert row("m",{"expected":"A|B"},["C","B"],"B")["rank"]==2
    assert metrics([])["selection_accuracy"] is None

def test_paired_conflicts_excluded():
    r={"baseline":{"candidates":[{"template_id":"B"},{"template_id":"A"}],"template_id":"B","preset_id":None},
       "ablation_rankings":{"title_dense":["B","A"],"keyword_dense_no_structure":["A","B"]},
       "candidates":[{"template_id":"A","structural_conflict":False},{"template_id":"B","structural_conflict":True}],
       "template_id":"A","preset_id":"p"}
    rows=paired_case({"expected":"A"},r)
    assert len(rows)==4
    assert aggregate(rows)["sap_aware"]["selection_accuracy"]==1
    assert aggregate(rows)["title_rule"]["mrr"]==.5
