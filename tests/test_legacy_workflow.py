from pathlib import Path
import json
import sys
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tfl_agent.tools.llm_client import FixtureJSONClient
from tfl_agent.agent.workflow import run_agent
from tfl_agent.agent.step1_parser import parse_inputs
from tfl_agent.agent.step3_retriever import retrieve_templates
from tfl_agent.tools.library_loader import load_library
from tfl_agent.tools.io_utils import read_json,write_json
from tfl_agent.tools.docx_editor import plan_modifications
SCHEMA_PATH = ROOT / "schemas" / "TFL_Specification.schema.json"

@pytest.fixture
def paths():
    return {'sap':ROOT/'input'/'synthetic_sap.pdf',
            'fixture':ROOT/'examples'/'demo_llm_output.json',
            'library':ROOT/'library','prompts':ROOT/'prompts'}

def execute(paths,out,fixture_path=None,**kwargs):
    return run_agent(sap_path=paths['sap'],library_path=kwargs.get('library',paths['library']),
        output_dir=out,llm=FixtureJSONClient(fixture_path or paths['fixture']),
        schema_path=SCHEMA_PATH,prompts_dir=paths['prompts'],
        tfl_id=kwargs.get('tfl_id',None if kwargs.get('content_list_path') else '14.2.1'),
        title=kwargs.get('title',None if kwargs.get('content_list_path') else 'Summary of Overall Survival'),
        content_list_path=kwargs.get('content_list_path'))

def test_full_mvp_synthetic_without_content_list(paths,tmp_path):
    report=execute(paths,tmp_path)
    assert report['generated']==1
    assert report['schema_and_evidence']['schema_valid']
    shell=tmp_path/'shells'/'Table_14.2.1.docx'
    assert shell.is_file()
    records=read_json(tmp_path/'TFL_Specification.json')
    assert records['study']['content_list_filename']==''
    assert records['coverage']['content_list_count']==0
    assert records['specifications'][0]['provenance']['field_links']
    assert read_json(tmp_path/'validation'/'14.2.1_docx.json')['valid']

def test_with_optional_content_list(paths,tmp_path):
    report=execute(paths,tmp_path,content_list_path=ROOT/'examples'/'content_list.json')
    assert report['generated']==1
    assert read_json(tmp_path/'TFL_Specification.json')['coverage']['content_list_count']==1

def test_invalid_quote_does_not_survive(paths,tmp_path):
    fixture=read_json(paths['fixture'])
    for claim in fixture['extraction']['claims']:
        if claim['json_pointer']=='/statistical_requirements/analysis_methods/0':
            claim['exact_quote']='THIS TEXT IS NOT IN THE SOURCE PDF'
    bad=tmp_path/'bad.json';write_json(bad,fixture)
    report=execute(paths,tmp_path/'bad_run',fixture_path=bad)
    assert report['generated']==0
    assert report['statuses']['14.2.1']=='needs_review'
    spec=read_json(tmp_path/'bad_run'/'TFL_Specification.json')['specifications'][0]
    assert spec['statistical_requirements']['analysis_methods']==[]
    assert spec['readiness']=='blocked'
    assert not list((tmp_path/'bad_run'/'shells').glob('*.docx')) if (tmp_path/'bad_run'/'shells').exists() else True

def test_wrong_type_does_not_generate(paths,tmp_path):
    write_json(tmp_path/'list.json',[{'tfl_id':'14.3.1','title':'Subject listings','output_type':'listing'}])
    report=execute(paths,tmp_path/'out',content_list_path=tmp_path/'list.json')
    assert report['statuses']['14.3.1']=='unsupported_mvp_type'
    assert report['generated']==0

def test_missing_docx_placeholders_blocks_generation(paths,tmp_path):
    from docx import Document
    lib=tmp_path/'lib'
    (lib/'templates'/'table').mkdir(parents=True)
    (lib/'metadata').mkdir()
    doc=Document();doc.add_paragraph('Static title; NOT a dynamic placeholder')
    doc.add_table(rows=1,cols=2)
    doc.save(lib/'templates'/'table'/'static.docx')
    metadata=read_json(paths['library']/'metadata'/'Template_Metadata.json')
    metadata['templates'][0]['identity']['file_path']='table/static.docx'
    write_json(lib/'metadata'/'Template_Metadata.json',metadata)
    report=execute(paths,tmp_path/'result',library=lib)
    assert report['statuses']['14.2.1']=='needs_review'
    assert not (tmp_path/'result'/'shells'/'Table_14.2.1.docx').exists()

def test_path_traversal_is_rejected(paths,tmp_path):
    lib=tmp_path/'lib';(lib/'metadata').mkdir(parents=True)
    metadata=read_json(paths['library']/'metadata'/'Template_Metadata.json')
    metadata['templates'][0]['identity']['file_path']='../../secret.docx'
    write_json(lib/'metadata'/'Template_Metadata.json',metadata)
    with pytest.raises(ValueError,match='Unsafe'):
        load_library(lib)

def test_evidence_no_invented_blocks(paths,tmp_path):
    # Block IDs that the retriever never selected (or do not exist) are rejected.
    fixture=read_json(paths['fixture'])
    fixture['extraction']['claims'][0]['block_id']='sap:p999:b0'
    bad=tmp_path/'bad_ids.json';write_json(bad,fixture)
    report=execute(paths,tmp_path/'out',fixture_path=bad)
    assert report['generated']==1 or report['statuses']['14.2.1']=='needs_review'
    spec=read_json(tmp_path/'out'/'TFL_Specification.json')['specifications'][0]
    assert any(x['issue_type']=='unsupported' for x in spec['issues'])
    assert all(e['ref_id']!='sap:p999:b0' for e in spec['provenance']['evidence'])
