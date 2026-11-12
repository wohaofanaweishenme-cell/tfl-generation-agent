"""Synthetic regression scenarios for evidence-safe, family-aware Table retrieval.

Do not commit real trial SAP text or API responses to GitHub.
"""
from copy import deepcopy
from tfl_agent.agent.step2_spec_builder import build_specification_from_extraction
from tfl_agent.agent.step3_retriever import retrieve_templates, select_template


def _empty_stats(**updates):
    base = {
        'analysis_topic': None, 'endpoint_name': None, 'endpoint_type': None,
        'analysis_population': [], 'analysis_methods': [], 'treatment_groups': [],
        'treatment_comparisons': [], 'visits_or_timepoints': [],
        'statistics_to_display': [], 'variables_to_display': [],
        'stratification_factors': [], 'notes': [],
    }
    return {**base, **updates}


def _table(**updates):
    return {**{'row_requirements': [], 'column_requirements': [],
               'footnote_requirements': [], 'denominator_rule': None}, **updates}


def _example_sap():
    blocks = [
        {'block_id': 'b0', 'page': 1, 'section': 'Analysis',
         'text': 'In the Safety Analysis Set, summarize n, mean, standard deviation, median, minimum and maximum. '
                 'Demographic variables include age, race, gender and height. '
                 'The groups are 800 mg BID and 1200 mg BID.'},
        {'block_id': 'b1', 'page': 2, 'section': 'Efficacy',
         'text': 'The ITT Population is used for the PFS summary table. '
                 'The PP Population is used for a different table.'},
    ]
    return {'filename': 'synthetic_source.pdf', 'pages': 2, 'blocks': blocks}


def _claim(path, quote, block='b0'):
    return {'json_pointer': path, 'block_id': block,
            'exact_quote': quote, 'derivation': 'explicit'}


def test_enumerated_statistics_and_variables_share_only_literal_verified_quote():
    sap = _example_sap()
    raw = {
        'statistical_requirements': _empty_stats(
            analysis_population=['Safety Analysis Set'],
            analysis_methods=['Descriptive statistics'],
            treatment_groups=['800 mg BID', '1200 mg BID'],
            statistics_to_display=['n', 'mean', 'standard deviation', 'median',
                                   'minimum', 'maximum', 'hazard ratio'],
            variables_to_display=['age', 'race', 'gender', 'height', 'invented variable'],
        ),
        'table_requirements': _table(
            row_requirements=['age'], column_requirements=['800 mg BID', '1200 mg BID']),
        'claims': [
            _claim('/statistical_requirements/analysis_population/0', 'the Safety Analysis Set'),
            _claim('/statistical_requirements/analysis_methods/0', 'summarize n, mean, standard deviation, median, minimum and maximum'),
            _claim('/statistical_requirements/treatment_groups/0', '800 mg BID'),
            _claim('/statistical_requirements/treatment_groups/1', '1200 mg BID'),
            _claim('/statistical_requirements/statistics_to_display/0', 'n, mean, standard deviation, median, minimum and maximum'),
            _claim('/statistical_requirements/variables_to_display/0', 'Demographic variables include age, race, gender and height'),
            _claim('/table_requirements/row_requirements/0', 'Demographic variables include age, race, gender and height'),
            _claim('/table_requirements/column_requirements/0', '800 mg BID'),
            _claim('/table_requirements/column_requirements/1', '1200 mg BID'),
        ], 'issues': []
    }
    tfl = {'tfl_id':'14.1.3.1', 'title':'Demographic and Baseline Characteristics – Safety Analysis Set', 'order':1}
    spec = build_specification_from_extraction(tfl, sap, raw, sap['blocks'])
    assert spec['readiness'] == 'needs_review'  # invented claims must remain flagged
    assert spec['statistical_requirements']['statistics_to_display'] == [
        'n','mean','standard deviation','median','minimum','maximum'
    ]
    assert spec['statistical_requirements']['variables_to_display'] == ['age','race','gender','height']
    assert spec['statistical_requirements']['endpoint_name'] is None
    assert not any(i['json_pointer'] == '/statistical_requirements/endpoint_name'
                   for i in spec['issues'])
    normalized_links = [x for x in spec['provenance']['field_links']
                        if x['note'] and 'enumeration' in x['note']]
    assert len(normalized_links) >= 7
    assert all(x['ref_ids'] == ['b0'] for x in normalized_links)
    assert any('hazard ratio' not in x for x in spec['statistical_requirements']['statistics_to_display'])
    assert any(i['issue_type']=='unsupported' for i in spec['issues'])


def test_invalid_quote_cannot_be_used_to_infer_sibling_items():
    sap = _example_sap()
    raw = {
        'statistical_requirements': _empty_stats(statistics_to_display=['n','mean']),
        'table_requirements': _table(),
        'claims': [_claim('/statistical_requirements/statistics_to_display/0', 'not in the source')],
        'issues': []
    }
    spec = build_specification_from_extraction(
        {'tfl_id': '14.1.3.1', 'title': 'Demographic Baseline', 'order': 1},
        sap, raw, sap['blocks'])
    assert spec['statistical_requirements']['statistics_to_display'] == []
    assert spec['readiness'] == 'blocked'


def test_explicit_itt_table_excludes_pp_population_without_dangling_links():
    sap = _example_sap()
    raw = {
        'statistical_requirements': _empty_stats(
            endpoint_name='Progression Free Survival',
            analysis_population=['ITT Population','PP Population'],
            analysis_methods=['Kaplan-Meier'],
            treatment_groups=['800 mg BID','1200 mg BID'],
            statistics_to_display=['median'],
        ),
        'table_requirements': _table(row_requirements=['median'], column_requirements=['800 mg BID']),
        'claims': [
            _claim('/statistical_requirements/analysis_population/0','ITT Population','b1'),
            _claim('/statistical_requirements/analysis_population/1','PP Population','b1'),
        ], 'issues': []
    }
    spec = build_specification_from_extraction(
        {'tfl_id':'14.2.3.1','title':'Summary of Progression Free Survival – ITT Analysis Set', 'order':1},
        sap, raw, sap['blocks'])
    assert spec['statistical_requirements']['analysis_population'] == ['ITT Population']
    assert any('Removed 1' in x['description'] for x in spec['issues'])
    assert '/statistical_requirements/analysis_population/1' not in [
        x['json_pointer'] for x in spec['provenance']['field_links']]


def _template(tid, title, *, endpoint=None, methods=None, stats=None, population=''):
    return {
        'identity': {'template_id':tid, 'output_type':'table', 'normalized_title':title},
        'source': {'study_id':'synthetic_library'},
        'statistical_context': {'endpoint_name':endpoint, 'analysis_methods':methods or [],
                                'analysis_population':[population] if population else []},
        'retrieval': {'keywords':[], 'aliases':[], 'retrieval_text':''},
        'table_spec': {'statistics':stats or [], 'rows':[]},
        'resolved_path': f'/tmp/{tid}.docx',
    }


def _target(title, endpoint, stats, methods, population='Safety Analysis Set'):
    return {
        'identity': {'output_type':'table','title':title},
        'statistical_requirements': {
            'endpoint_name': endpoint, 'analysis_topic': None,
            'analysis_methods': methods, 'analysis_population': [population],
            'statistics_to_display': stats,
        },
        'table_requirements': {'row_requirements':stats, 'column_requirements':[]},
    }


def test_demographics_beats_unrelated_ae_even_without_endpoint_metadata():
    target = _target('Demographic and Baseline Characteristics – Safety Analysis Set',
                     None, ['n','mean','SD','median','percentages'], ['Descriptive statistics'])
    lib = {'index':{}, 'templates':[
        _template('AE','Treatment-Emergent Adverse Events by Preferred Term',stats=['n (%)']),
        _template('DEMO','Demographic and Baseline Characteristics (ITT Set)',
                  stats=['n','Mean','SD','Median','n (%)'], population='ITT'),
    ]}
    candidates = retrieve_templates(target, lib)
    assert candidates[0]['template_id'] == 'DEMO'
    assert candidates[0]['score'] > 0.55
    assert candidates[0]['population_change_required']
    assert select_template(candidates)['template_id'] == 'DEMO'
    assert not any(x['template_id'] == 'AE' for x in candidates)


def test_pfs_ranks_os_time_to_event_but_not_auto_select_cross_endpoint():
    target = _target('Summary of Progression Free Survival – ITT Analysis Set',
                     'Progression Free Survival (PFS)', ['Q1','Median','Q3','95% CI'],
                     ['Kaplan-Meier','Brookmeyer-Crowley'], 'ITT')
    lib = {'index': {}, 'templates': [
        _template('AE','Treatment-Emergent Adverse Events by System Organ Class',stats=['n (%)']),
        _template('OS','Overall Survival (ITT Set)', endpoint='Overall Survival',
                  methods=['Kaplan-Meier','Brookmeyer-Crowley'],stats=['Median','95% CI'],population='ITT'),
    ]}
    candidates = retrieve_templates(target, lib)
    assert candidates[0]['template_id'] == 'OS'
    assert candidates[0]['table_family'] == 'time_to_event'
    assert candidates[0]['cross_endpoint']
    assert select_template(candidates) is None
    assert not any(x['template_id'] == 'AE' for x in candidates)
