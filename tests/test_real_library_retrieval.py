"""Integration ranking checks on teammate v2.4 library, if checked out.

Source files remain read-only. This test does NOT send content to any API.
"""
from pathlib import Path
import pytest
from tfl_agent.tools.library_loader import load_library
from tfl_agent.agent.step3_retriever import retrieve_templates, select_template

ROOT = Path(__file__).resolve().parents[1]


def test_actual_study_demographics_and_pfs_rankings():
    folder = ROOT / 'library' / 'studies' / 'P-VCNA-003'
    if not folder.is_dir():
        pytest.skip('Real study library is in the GitHub checkout, not the offline dev ZIP')
    library = load_library(folder)
    demographics = {
        'identity': {'title': 'Demographic and Baseline Characteristics – Safety Analysis Set',
                     'output_type': 'table'},
        'statistical_requirements': {
            'analysis_topic':None, 'endpoint_name':None, 'analysis_population':['Safety Analysis Set'],
            'analysis_methods':['Descriptive statistics','Frequencies and percentages'],
            'statistics_to_display':['n','Mean','SD','Median','Minimum','Maximum','percentages'],
        },
        'table_requirements': {'row_requirements':['Age','Race','Height'], 'column_requirements':[]},
    }
    ranked = retrieve_templates(demographics, library, top_k=5)
    assert ranked and ranked[0]['template_id'] == 'PVCNA003_T_14_1_2_1'
    assert ranked[0]['table_family'] == 'demographics'
    assert ranked[0]['score'] >= 0.55
    assert select_template(ranked) is not None

    pfs = {
        'identity': {'title': 'Summary of Progression Free Survival – ITT Analysis Set',
                     'output_type': 'table'},
        'statistical_requirements': {
            'analysis_topic':None, 'endpoint_name':'Progression Free Survival (PFS)',
            'analysis_population':['ITT Population'],
            'analysis_methods':['Kaplan-Meier','Brookmeyer-Crowley'],
            'statistics_to_display':['Q1','Median','Q3','95% CI','censored patients'],
        },
        'table_requirements': {'row_requirements':['Number of patients with progression or death'],
                               'column_requirements':[]},
    }
    other = retrieve_templates(pfs, library, top_k=5)
    assert other and other[0]['table_family'] == 'time_to_event'
    assert all(x['table_family'] != 'adverse_events' for x in other)
    assert other[0]['cross_endpoint']  # source OS != target PFS; not auto-approved
    assert select_template(other) is None
