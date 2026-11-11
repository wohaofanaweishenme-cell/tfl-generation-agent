"""Five-step TFL MVP. Failure for one TFL never silently becomes success."""
import json
from pathlib import Path
from tfl_agent.agent.step1_parser import parse_inputs
from tfl_agent.agent.step2_spec_builder import build_specification
from tfl_agent.agent.step3_retriever import retrieve_templates,select_template
from tfl_agent.agent.step4_generator import generate
from tfl_agent.agent.step5_validator import validate_spec_document,validate_shell
from tfl_agent.tools.library_loader import load_library
from tfl_agent.tools.io_utils import write_json


def safe_name(name):
    return ''.join(c if c.isalnum() or c in '._-' else '_' for c in name)

def run_agent(*,sap_path,library_path,output_dir,llm,schema_path,prompts_dir,
              content_list_path=None,tfl_id=None,title=None,max_tfl=1,allow_review=False):
    out=Path(output_dir).resolve();out.mkdir(parents=True,exist_ok=True)
    # Step 1
    sap,inventory,identification_mode=parse_inputs(sap_path,content_list_path,tfl_id,title)
    library=load_library(library_path)
    if max_tfl<1:raise ValueError('max_tfl must be positive')
    selected_inventory=inventory[:max_tfl]
    write_json(out/'parsed_sap_blocks.json',sap)
    write_json(out/'target_inventory.json',{'identification_mode':identification_mode,
                'full_study_coverage_asserted':False,'targets':inventory,
                'mvp_processing_limit':max_tfl})
    all_specs=[];result_records=[];unparsed=[]
    for tfl in selected_inventory:
        record={'tfl_id':tfl['tfl_id'],'title':tfl['title'],'status':'pending','template_id':None,
                'shell_path':None,'review_reasons':[]}
        try:
            if tfl['output_type']!='table':
                record['status']='unsupported_mvp_type';record['review_reasons']=['MVP generates table shells only']
                unparsed.append(tfl['tfl_id']);result_records.append(record);continue
            # Step 2
            spec,debug=build_specification(tfl,sap,llm,prompts_dir)
            all_specs.append(spec)
            write_json(out/'evidence'/f'{safe_name(tfl["tfl_id"])}_retrieval.json',debug)
            write_json(out/'specifications'/f'{safe_name(tfl["tfl_id"])}.json',spec)
            # Step 3
            matches=retrieve_templates(spec,library)
            selection=select_template(matches)
            record['candidate_templates']=[{k:v for k,v in m.items() if k not in ['template','source_path']} for m in matches]
            if spec['readiness']!='ready':
                record['status']='needs_review';record['review_reasons']=[i['description'] for i in spec['issues']]
                # Conservative default: even --allow-review does not override a blocked spec.
                if spec['readiness']=='blocked' or not allow_review:
                    result_records.append(record);continue
                record['review_reasons'].append('Draft allowed by explicit --allow-review; not approved output.')
            if not selection:
                record['status']='needs_review'
                record['review_reasons'].append('No unique template exceeds matching threshold')
                result_records.append(record);continue
            record['template_id']=selection['template_id'];record['retrieval_score']=selection['score']
            # Step 4
            shell_path=out/'shells'/f'Table_{safe_name(tfl["tfl_id"])}.docx'
            shell,plan=generate(spec,selection,shell_path)
            write_json(out/'modification_plans'/f'{safe_name(tfl["tfl_id"])}.json',plan)
            if not shell:
                record['status']='needs_review'
                record['review_reasons'].append('DOCX template is not safely editable with verified placeholders')
                record['review_reasons'].extend('Missing: '+x for x in plan['missing_placeholders'])
                record['review_reasons'].extend('Unexpected: '+x for x in plan['unexpected_placeholders'])
                result_records.append(record);continue
            # Step 5
            report=validate_shell(shell,spec,plan)
            write_json(out/'validation'/f'{safe_name(tfl["tfl_id"])}_docx.json',report)
            record['shell_path']=shell
            record['status']=('generated' if report['valid'] and spec['readiness']=='ready' else 'draft_needs_review') if report['valid'] else 'validation_failed'
            if not report['valid']:record['review_reasons'].extend(report['issues'])
        except Exception as e:
            record['status']='failed';record['review_reasons'].append(f'{type(e).__name__}: {e}')
        result_records.append(record)
    # Record TFLs skipped by the explicit MVP processing limit.
    for tfl in inventory[max_tfl:]:
        result_records.append({'tfl_id':tfl['tfl_id'],'title':tfl['title'],
                               'status':'not_processed_mvp_limit','template_id':None,'shell_path':None,
                               'review_reasons':['MVP max_tfl limit']})
        unparsed.append(tfl['tfl_id'])
    aggregate={'study':{'study_id':None,'sap_filename':sap['filename'],'sap_version':None,
                        'content_list_filename':Path(content_list_path).name if content_list_path else ''},
               'specifications':all_specs,
               'coverage':{'content_list_count':len(inventory) if content_list_path else 0,
                           'specification_count':len(all_specs),'unparsed_entries':unparsed}}
    schema_validation=validate_spec_document(aggregate,schema_path,sap)
    write_json(out/'TFL_Specification.json',aggregate)
    write_json(out/'TFL_Inventory.json',{'identification_mode':identification_mode,'records':result_records})
    write_json(out/'Generation_Rationale.json',[{'tfl_id':r['tfl_id'],'status':r['status'],
                   'template_id':r.get('template_id'),'retrieval_score':r.get('retrieval_score'),
                   'reasons':r['review_reasons']} for r in result_records])
    report={'schema_and_evidence':schema_validation,
            'generated':sum(r['status']=='generated' for r in result_records),
            'needs_review':sum(r['status'] in ['needs_review','draft_needs_review'] for r in result_records),
            'failed':sum(r['status'] in ['failed','validation_failed'] for r in result_records),
            'statuses':{r['tfl_id']:r['status'] for r in result_records},
            'note':'No clinical/statistical correctness certification: direct quotation checks are not semantic proof.'}
    write_json(out/'validation_report.json',report)
    if not schema_validation['schema_valid']:
        for r in result_records:
            if r['status']=='generated':
                r['status']='validation_failed'
                r['review_reasons'].append('Aggregate schema or evidence validation failed')
        write_json(out/'TFL_Inventory.json',{'identification_mode':identification_mode,'records':result_records})
        write_json(out/'Generation_Rationale.json',[{'tfl_id':r['tfl_id'],'status':r['status'],
                   'template_id':r.get('template_id'),'reasons':r['review_reasons']} for r in result_records])
        report['generated']=0;report['failed']=sum(r['status'] in ['failed','validation_failed'] for r in result_records)
        report['statuses']={r['tfl_id']:r['status'] for r in result_records}
        write_json(out/'validation_report.json',report)
    return report
