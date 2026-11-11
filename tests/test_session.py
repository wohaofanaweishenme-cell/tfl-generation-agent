from pathlib import Path
import pytest
from tfl_agent import TFLSession
from tfl_agent.tools.llm_client import FixtureJSONClient
from tfl_agent.tools.io_utils import read_json

ROOT=Path(__file__).resolve().parents[1]

def make_session(tmp_path, **kwargs):
    return TFLSession(
        sap_path=ROOT/'input'/'synthetic_sap.pdf',
        library_path=kwargs.get('library_path',ROOT/'library'),
        schema_path=ROOT/'schemas'/'TFL_Specification.schema.json',
        prompts_dir=ROOT/'prompts',
        output_dir=tmp_path,
        llm=FixtureJSONClient(ROOT/'examples'/'demo_llm_output.json'),
        content_list_path=kwargs.get('content_list_path'),
        tfl_id=None if kwargs.get('content_list_path') else '14.2.1',
        title=None if kwargs.get('content_list_path') else 'Summary of Overall Survival',
    )

def test_steps_produce_audited_docx(tmp_path):
    s=make_session(tmp_path)
    parsed=s.step1_parse()
    assert parsed['block_count'] > 0
    spec=s.step2_build_specification()
    assert spec['readiness']=='ready'
    assert s.spec_validation['schema_valid']
    results=s.step3_retrieve_templates()
    assert results['selected_template_id']=='TBL_DEMO_OS'
    plan=s.preview_modification_plan()
    assert plan['safe_to_generate']
    generated=s.step4_generate_shell()
    assert generated['status']=='generated'
    assert Path(generated['shell_path']).is_file()
    report=s.step5_validate_and_export()
    assert report['generated']==1
    assert report['word_validation']['valid']
    assert read_json(tmp_path/'TFL_Specification.json')['coverage']['specification_count']==1

def test_optional_content_list(tmp_path):
    s=make_session(tmp_path,content_list_path=ROOT/'examples'/'content_list.json')
    s.step1_parse();s.step2_build_specification();s.step3_retrieve_templates();s.step4_generate_shell()
    report=s.step5_validate_and_export()
    assert report['generated']==1
    assert read_json(tmp_path/'TFL_Specification.json')['coverage']['content_list_count']==1

def test_out_of_order_raises(tmp_path):
    s=make_session(tmp_path)
    with pytest.raises(RuntimeError,match='Step 1'):
        s.step2_build_specification()
