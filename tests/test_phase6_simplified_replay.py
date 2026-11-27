import pytest
from copy import deepcopy
from tfl_agent.agent.phase6_simplified_replay import normalize

@pytest.fixture
def example():
    p={'target':{'title':'Counts by category','output_type':'table'},'library':{'templates':[{'template_id':'A','presets':[{'preset_id':'PA'}]},{'template_id':'B','presets':[]}]},'sap_evidence':[{'chunk_id':'c1','text':'Counts by category will be reported.'}]}
    c={'source':'sap','chunk_id':'c1','exact_quote':'Counts by category','applicability':'target_specific','discrimination':'supports_candidate_over_alternative','competing_template':'B','use':'structural_support'}
    o={'ranking':['A'],'recommended_template':'A','supported_template':'A','selection_status':'candidate_only','proposed_preset':'PA','reason':'category structure','candidate_assessments':[{'template_id':'A','compatibility':'supported','reason':'categories rather than hierarchy','missing_information':[],'citations':[c]}]}
    return o,p

def test_partial_is_not_completed(example):
    o,p=example; d=normalize(o,p)
    assert d['protocol_valid'] and d['rank_prefix']==['A'] and d['unranked_templates']==['B']
    assert not d['complete_ranking'] and d['protocol_supported_template']=='A'
    assert not d['citations'][0]['citation_reason_present'] and 'reason' not in d['citations'][0]
    assert not d['semantic_applicability_verified'] and not d['generation_authorized']

def test_uncertainty_is_not_promoted(example):
    o,p=example;o.update(supported_template=None,selection_status='uncertain');o['candidate_assessments'][0]['compatibility']='uncertain'
    d=normalize(o,p);assert d['protocol_valid'] and d['protocol_supported_template'] is None

def test_no_compatible(example):
    o,p=example;o.update(recommended_template=None,supported_template=None,proposed_preset=None,selection_status='no_compatible_template');o['candidate_assessments'][0]['compatibility']='incompatible';o['candidate_assessments'][0]['citations']=[]
    d=normalize(o,p);assert d['protocol_valid'] and d['recommended_template'] is None

@pytest.mark.parametrize('mutation',['bad_quote','bad_chunk','other_endpoint','mixed_counterevidence','bad_preset','duplicate_rank','unknown_rank','missing_reason','unjustified_override','wrong_competitor'])
def test_invalid_is_not_silently_repaired(example,mutation):
    o,p=example;c=o['candidate_assessments'][0]['citations'][0]
    if mutation=='bad_quote':c['exact_quote']='invented'
    elif mutation=='bad_chunk':c['chunk_id']='missing'
    elif mutation=='other_endpoint':c['applicability']='other_endpoint_or_output'
    elif mutation=='mixed_counterevidence':c.update(applicability='mixed',discrimination='contradicts_candidate',use='counterevidence')
    elif mutation=='bad_preset':o['proposed_preset']='PB'
    elif mutation=='duplicate_rank':o['ranking']=['A','A']
    elif mutation=='unknown_rank':o['ranking']=['A','X']
    elif mutation=='missing_reason':o['candidate_assessments'][0].pop('reason')
    elif mutation=='unjustified_override':o['title_hypothesis']='B';c.update(source='title',chunk_id=None,applicability='title_explicit')
    elif mutation=='wrong_competitor':c['competing_template']='A'
    d=normalize(o,p);assert not d['protocol_valid'] and d['protocol_supported_template'] is None

def test_bad_alternative_blocks_support_not_ranking(example):
    o,p=example;c=deepcopy(o['candidate_assessments'][0]['citations'][0]);c.update(competing_template='A',use='counterevidence',applicability='mixed',discrimination='contradicts_candidate')
    o['ranking'].append('B');o['candidate_assessments'].append({'template_id':'B','compatibility':'uncertain','reason':'other layout','missing_information':[],'citations':[c]})
    d=normalize(o,p);assert d['complete_ranking'] and d['recommended_template']=='A' and d['protocol_supported_template'] is None
