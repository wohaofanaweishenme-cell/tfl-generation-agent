"""Jupyter-facing, step-by-step API. Business logic stays in agent/ and tools/."""
from __future__ import annotations
from pathlib import Path
from typing import Any

from tfl_agent.agent.step1_parser import parse_inputs
from tfl_agent.agent.step2_spec_builder import build_specification
from tfl_agent.agent.step3_retriever import retrieve_templates, template_selection_decision
from tfl_agent.agent.step4_generator import generate
from tfl_agent.agent.step5_validator import validate_spec_document, validate_shell
from tfl_agent.tools.docx_editor import plan_modifications
from tfl_agent.tools.io_utils import write_json
from tfl_agent.tools.library_loader import load_library


def _safe_file_id(value: str) -> str:
    return ''.join(c if c.isalnum() or c in '._-' else '_' for c in value)


class TFLSession:
    """Interactive state holder for ONE target TFL. Does not modify the source Library.

    Methods correspond exactly to the notebook's five visible workflow steps.
    The user can inspect or revise data between steps; no LLM calls in this wrapper.
    Actual LLM calls happen only in build_specification on Step 2.
    """

    def __init__(self, *, sap_path, library_path, schema_path, prompts_dir,
                 output_dir, llm, content_list_path=None, tfl_id=None,
                 title=None, tfl_index=0, allow_review=False, sap_body_page_range=None,
                 reviewed_adaptation=None):
        self.sap_path=Path(sap_path).resolve()
        self.library_path=Path(library_path).resolve()
        self.schema_path=Path(schema_path).resolve()
        self.prompts_dir=Path(prompts_dir).resolve()
        self.output_dir=Path(output_dir).resolve()
        self.content_list_path=Path(content_list_path).resolve() if content_list_path else None
        self.llm=llm
        self.tfl_id=tfl_id
        self.title=title
        self.tfl_index=tfl_index
        self.allow_review=allow_review
        self.reviewed_adaptation=reviewed_adaptation
        self.sap_body_page_range=sap_body_page_range
        self.sap: dict[str,Any]|None=None
        self.inventory: list[dict]|None=None
        self.identification_mode: str|None=None
        self.tfl: dict|None=None
        self.library: dict|None=None
        self.spec: dict|None=None
        self.spec_debug: dict|None=None
        self.spec_validation: dict|None=None
        self.matches: list[dict]|None=None
        self.selection: dict|None=None
        self.selection_decision: dict|None=None
        self.shell_path: str|None=None
        self.plan: dict|None=None
        self.shell_status: str|None=None

    def _require(self, attr, stage):
        if getattr(self,attr) is None:
            raise RuntimeError(f"Run {stage} first, before this step.")

    def _aggregate(self):
        self._require('spec','Step 2')
        inventory=self.inventory or []
        return {
            'study': {
                'study_id':None,
                'sap_filename':self.sap['filename'],
                'sap_version':None,
                'content_list_filename':self.content_list_path.name if self.content_list_path else '',
            },
            'specifications':[self.spec],
            'coverage': {
                'content_list_count': len(inventory) if self.content_list_path else 0,
                'specification_count':1,
                'unparsed_entries':[x['tfl_id'] for x in inventory if x['tfl_id']!=self.tfl['tfl_id']],
            },
        }

    def step1_parse(self):
        self.sap,self.inventory,self.identification_mode=parse_inputs(
            self.sap_path,self.content_list_path,self.tfl_id,self.title)
        if self.sap_body_page_range is not None:
            a,b=self.sap_body_page_range
            if not (isinstance(a,int) and isinstance(b,int) and 1<=a<=b<=self.sap['pages']):
                raise ValueError('sap_body_page_range must be physical PDF pages (start,end) within this PDF')
            self.sap['blocks']=[x for x in self.sap['blocks'] if a<=x['page']<=b]
            if not self.sap['blocks']:
                raise ValueError('No selectable SAP body text in the requested PDF page range')
        self.library=load_library(self.library_path)
        if not 0<=self.tfl_index<len(self.inventory):
            raise IndexError('tfl_index is out of range for the identified target inventory')
        self.tfl=self.inventory[self.tfl_index]
        self.output_dir.mkdir(parents=True,exist_ok=True)
        write_json(self.output_dir/'parsed_sap_blocks.json',self.sap)
        write_json(self.output_dir/'target_inventory.json',{
            'identification_mode':self.identification_mode,
            'full_study_coverage_asserted':False,
            'targets':self.inventory,
            'selected_tfl_id':self.tfl['tfl_id'],
        })
        return {
            'sap_filename':self.sap['filename'],
            'page_count':self.sap['pages'],
            'block_count':len(self.sap['blocks']),
            'identification_mode':self.identification_mode,
            'target_count':len(self.inventory),
            'selected_target':self.tfl,
            'loaded_templates':len(self.library['templates']),
            'library_format':self.library['format'],
            'library_index_mode':self.library['index_mode'],
            'sap_body_page_range':self.sap_body_page_range,
        }

    def step2_build_specification(self):
        self._require('sap','Step 1')
        if self.tfl['output_type']!='table':
            raise NotImplementedError('MVP supports table shells only; Figure/Listing remain unsupported.')
        self.spec,self.spec_debug=build_specification(self.tfl,self.sap,self.llm,self.prompts_dir)
        self.spec_validation=validate_spec_document(self._aggregate(),self.schema_path,self.sap)
        ident=_safe_file_id(self.tfl['tfl_id'])
        write_json(self.output_dir/'evidence'/f'{ident}_retrieval.json',self.spec_debug)
        write_json(self.output_dir/'specifications'/f'{ident}.json',self.spec)
        write_json(self.output_dir/'validation'/f'{ident}_specification.json',self.spec_validation)
        return self.spec

    def step3_retrieve_templates(self,top_k=5,min_score=0.55):
        self._require('spec','Step 2')
        self.matches=retrieve_templates(self.spec,self.library,top_k=top_k)
        self.selection_decision=template_selection_decision(self.matches,min_score=min_score)
        self.selection=self.selection_decision['selection']
        candidates=[{k:v for k,v in m.items() if k not in ('source_path','template')} for m in self.matches]
        status_fields={k:v for k,v in self.selection_decision.items() if k != 'selection'}
        result={'candidates':candidates, **status_fields}
        write_json(self.output_dir/'retrieval'/f'{_safe_file_id(self.tfl["tfl_id"])}_candidates.json',result)
        return result

    def _reviewed_source_selection(self):
        """An explicit review record may permit a *draft* from a blocked candidate.

        This does not alter Step 3's automatic selection decision.  Only an
        actual retrieved candidate can be used; the adapter validates the
        review fields and exact source anchors before any edits are made.
        """
        if self.selection is not None:
            return self.selection
        approval = self.reviewed_adaptation
        if not isinstance(approval, dict):
            return None
        required = ("template_id", "tfl_id", "reviewed_by", "review_reason")
        if any(not isinstance(approval.get(k), str) or not approval[k].strip()
               for k in required):
            return None
        if approval["tfl_id"] != self.tfl["tfl_id"]:
            return None
        return next((m for m in self.matches or []
                     if m["template_id"] == approval["template_id"]), None)

    def preview_modification_plan(self):
        self._require('matches','Step 3')
        selection = self._reviewed_source_selection()
        if selection is None:
            decision=self.selection_decision or {}
            return {'safe_to_generate':False,
                    'reason':'; '.join(decision.get('reasons', ['No reviewed source template available'])),
                    'retrieval_status':decision.get('status','no_candidate'),
                    'best_candidate_template_id':decision.get('best_candidate_template_id')}
        return plan_modifications(selection['source_path'],self.spec,
                                  locator_map_path=selection['template'].get('locator_map_path'),
                                  reviewed_adaptation=self.reviewed_adaptation)

    def step4_generate_shell(self):
        self._require('matches','Step 3')
        self.shell_path=None
        if not self.spec_validation['schema_valid']:
            self.shell_status='blocked_schema'
            return {'status':self.shell_status,'shell_path':None,'issues':self.spec_validation['errors']}
        if self.spec['readiness']=='blocked' or (self.spec['readiness']!='ready' and not self.allow_review):
            self.shell_status='needs_review'
            return {'status':self.shell_status,'shell_path':None,
                    'issues':[x['description'] for x in self.spec['issues']]}
        self.selection = self._reviewed_source_selection()
        if self.selection is None:
            self.shell_status='needs_review'
            return {'status':self.shell_status,'shell_path':None,
                    'issues':(self.selection_decision or {}).get('reasons',
                                                             ['No automatically usable template'])}
        path=self.output_dir/'shells'/f'Table_{_safe_file_id(self.tfl["tfl_id"])}.docx'
        self.shell_path,self.plan=generate(self.spec,self.selection,path,
                                           reviewed_adaptation=self.reviewed_adaptation)
        write_json(self.output_dir/'modification_plans'/f'{_safe_file_id(self.tfl["tfl_id"])}.json',self.plan)
        if self.shell_path is None:
            self.shell_status='needs_review'
            return {'status':self.shell_status,'shell_path':None,
                    'issues':[self.plan.get('reason','Unverified DOCX template placeholders')]+
                    [f'Missing: {x}' for x in self.plan['missing_placeholders']]+
                    [f'Unexpected: {x}' for x in self.plan['unexpected_placeholders']]}
        self.shell_status=('draft_needs_review'
                           if self.plan.get('editing_mode')=='verified_bookmark_draft'
                           or self.spec['readiness']!='ready'
                           else 'generated')
        return {'status':self.shell_status,'shell_path':self.shell_path,'issues':[]}

    def step5_validate_and_export(self):
        self._require('spec','Step 2')
        # Allows a clear failed report even when Step 4 intentionally did not generate.
        spec_validation=validate_spec_document(self._aggregate(),self.schema_path,self.sap)
        if self.shell_path and self.plan:
            word_validation=validate_shell(self.shell_path,self.spec,self.plan)
        else:
            word_validation={'valid':False,'checks':{},'issues':['Shell not generated; inspect Step 4 status']}
        status=self.shell_status or 'not_generated'
        if not spec_validation['schema_valid']:
            status='validation_failed'
        elif self.shell_path and not word_validation['valid']:
            status='validation_failed'
        record={
            'tfl_id':self.tfl['tfl_id'],'title':self.tfl['title'],'status':status,
            'template_id':self.selection['template_id'] if self.selection else None,
            'shell_path':self.shell_path,
            'best_candidate_template_id':(self.selection_decision or {}).get('best_candidate_template_id'),
            'retrieval_status':(self.selection_decision or {}).get('status'),
            'review_reasons':((self.selection_decision or {}).get('reasons', [])
                              if not self.selection else [])+
                             ([x['description'] for x in self.spec['issues']]
                               if self.spec['issues'] else [])+
                              (word_validation['issues'] if not word_validation['valid'] else []),
        }
        report={
            'schema_and_evidence':spec_validation,
            'word_validation':word_validation,
            'status':status,
            'generated':int(status=='generated'),
            'needs_review':int(status in ('needs_review','draft_needs_review')),
            'failed':int(status=='validation_failed'),
            'coverage_scope':'One selected TFL; complete-study coverage is not asserted',
            'note':'Verifiable source quotations do not prove clinical/statistical correctness.',
        }
        write_json(self.output_dir/'TFL_Specification.json',self._aggregate())
        write_json(self.output_dir/'TFL_Inventory.json',{
            'identification_mode':self.identification_mode,
            'full_study_coverage_asserted':False,
            'records':[record],
        })
        write_json(self.output_dir/'Generation_Rationale.json',{
            'tfl_id':self.tfl['tfl_id'],'selected_template_id':record['template_id'],
            'selected_template_explanation':self.selection.get('explanation') if self.selection else None,
            'best_candidate_template_id':(self.selection_decision or {}).get('best_candidate_template_id'),
            'retrieval_status':(self.selection_decision or {}).get('status'),
            'retrieval_review_reasons':(self.selection_decision or {}).get('reasons', []),
            'modification_plan':self.plan,
            'retrieval_candidates':[
                {k:v for k,v in m.items() if k not in ('source_path','template')}
                for m in (self.matches or [])
            ],
            'readiness':self.spec['readiness'],
            'issues':self.spec['issues'],
            'status':status,
        })
        write_json(self.output_dir/'validation_report.json',report)
        return report

    def run_all(self):
        self.step1_parse()
        self.step2_build_specification()
        self.step3_retrieve_templates()
        self.step4_generate_shell()
        return self.step5_validate_and_export()
