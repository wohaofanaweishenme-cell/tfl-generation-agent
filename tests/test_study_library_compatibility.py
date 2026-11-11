"""No network or API key required to verify the two Library layouts."""
import json
from pathlib import Path
from types import SimpleNamespace

from docx import Document
from docx.oxml import OxmlElement

from tfl_agent.tools.library_loader import load_library
from tfl_agent.tools.docx_editor import plan_modifications
from tfl_agent.agent.step3_retriever import retrieve_templates, select_template
from tfl_agent.tools.llm_client import DeepSeekJSONClient

ROOT = Path(__file__).resolve().parents[1]


def test_existing_fixture_library_still_loads():
    lib = load_library(ROOT / 'library')
    assert lib['format'] == 'mvp'
    assert lib['index_mode'] == 'global_keyword_index'
    assert len(lib['templates']) == 1


def make_study(tmp_path):
    root = tmp_path / 'P-VCNA-003'
    dest = root / 'TFL_Template_Library' / 'table'
    dest.mkdir(parents=True)
    # Create source-style DOCX with preserved text and a bookmark, NOT {{TOKENS}}.
    doc = Document()
    p = doc.add_paragraph('Table 14.2.1.1 Overall Survival (ITT)')
    start = OxmlElement('w:bookmarkStart')
    start.set('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}id', '42')
    start.set('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}name', 'O_O00001')
    end = OxmlElement('w:bookmarkEnd')
    end.set('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}id', '42')
    p._p.insert(0, start)
    p._p.append(end)
    doc.add_table(rows=2, cols=2).cell(0, 0).text = 'Median OS'
    doc.save(dest / 'PVCNA003_T_14_2_1_1.docx')
    (root / 'intermediate' / 'DOCX_Locator_Map').mkdir(parents=True)
    (root / 'intermediate' / 'DOCX_Locator_Map' / 'PVCNA003_T_14_2_1_1.json').write_text('{}')
    record = {
        'identity': {'template_id': 'PVCNA003_T_14_2_1_1', 'output_type': 'table',
                     'file_path': 'table/PVCNA003_T_14_2_1_1.docx',
                     'original_title': 'Overall Survival (ITT)',
                     'normalized_title': 'Overall Survival (ITT)'},
        'source': {'study_id': 'P-VCNA-003'},
        'statistical_context': {'endpoint_name': 'Overall Survival',
                                'analysis_methods': ['Kaplan-Meier']},
        'retrieval': {'keywords': ['overall survival', 'Kaplan-Meier'],
                      'aliases': [], 'retrieval_text': 'Median OS and survival probability'},
    }
    (root / 'Study_Metadata.json').write_text(json.dumps({'library_id': 'SOURCE_TEST', 'templates': [record]}))
    return root


def test_study_v24_loader_retrieval_and_safe_block(tmp_path):
    root = make_study(tmp_path)
    lib = load_library(root)
    assert lib['format'] == 'study_v2_4'
    assert lib['index_mode'] == 'per_template_keywords'
    assert lib['library_id'] == 'SOURCE_TEST'
    assert len(lib['templates']) == 1
    t = lib['templates'][0]
    assert t['locator_map_path'].endswith('PVCNA003_T_14_2_1_1.json')
    spec = {
        'identity': {'title': 'Overall Survival', 'tfl_id': '14.2.1.1', 'output_type': 'table'},
        'statistical_requirements': {'analysis_topic': 'Overall Survival',
                                     'endpoint_name': 'Overall Survival',
                                     'analysis_methods': ['Kaplan-Meier'],
                                     'statistics_to_display': ['Median OS']},
        'table_requirements': {'column_requirements': ['Group A'],
                               'row_requirements': ['Median OS'],
                               'footnote_requirements': []},
    }
    matches = retrieve_templates(spec, lib)
    assert matches[0]['template_id'] == t['identity']['template_id']
    assert matches[0]['source_study_id'] == 'P-VCNA-003'
    assert matches[0]['endpoint_match']
    assert select_template(matches) is matches[0]
    plan = plan_modifications(t['resolved_path'], spec, locator_map_path=t['locator_map_path'])
    assert plan['editing_mode'] == 'source_bookmarks_requires_adaptation'
    assert plan['bookmark_count'] > 0
    assert not plan['safe_to_generate']
    assert 'not yet been validated' in plan['reason']
    assert not list(root.rglob('Table_14*docx'))


def test_deepseek_json_client_uses_secret_and_rejects_blank(monkeypatch):
    class FakeCompletions:
        def __init__(self): self.kwargs = None; self.content = '{"queries": ["survival"]}'
        def create(self, **kwargs):
            self.kwargs = kwargs
            return SimpleNamespace(choices=[SimpleNamespace(
                finish_reason='stop', message=SimpleNamespace(content=self.content))])
    m = FakeCompletions()
    monkeypatch.setitem(__import__('sys').modules, 'openai', SimpleNamespace(OpenAI=lambda **kw: None))
    client = DeepSeekJSONClient(api_key='unit-test-placeholder')
    client.client = SimpleNamespace(chat=SimpleNamespace(completions=m))
    assert client.json('QUERY_PLANNER', 'survival')['queries'] == ['survival']
    assert m.kwargs['model'] == 'deepseek-flash'
    assert m.kwargs['response_format']['type'] == 'json_object'
    assert m.kwargs['extra_body'] == {'thinking': {'type': 'disabled'}}
    m.content = '  '
    import pytest
    with pytest.raises(RuntimeError, match='empty JSON'):
        client.json('EVIDENCE_EXTRACTOR', 'example')


def test_actual_checked_in_study_library_when_present():
    import pytest
    root = ROOT / 'library' / 'studies' / 'P-VCNA-003'
    if not root.exists():
        pytest.skip('Teammate study library is available only in the GitHub checkout')
    lib = load_library(root)
    assert lib['format'] == 'study_v2_4'
    assert len(lib['templates']) == 64
    type_counts = {kind: sum(t['identity']['output_type'] == kind for t in lib['templates'])
                   for kind in ('table', 'figure', 'listing')}
    assert type_counts == {'table': 25, 'figure': 2, 'listing': 37}
    assert all(Path(t['resolved_path']).is_file() for t in lib['templates'])
    assert all(t['locator_map_path'] and Path(t['locator_map_path']).is_file() for t in lib['templates'])
