"""Metadata-only invariants against immutable prior-stage snapshots and real DOCX bytes."""
import json,hashlib,collections
from pathlib import Path
from jsonschema import Draft202012Validator
r=Path(__file__).resolve().parents[1];meta=json.loads((r/'Study_Metadata.json').read_text());schema=json.loads((r/'schemas/Template_Metadata.schema.json').read_text());schemaerrors=[dict(path=list(x.path),message=x.message) for x in Draft202012Validator(schema).iter_errors(meta)];assert not schemaerrors,schemaerrors[:3]
physical=['footnote_id','marker','exact_text','applies_to','category','display_order','applies_to_refs','evidence_ref_ids'];records=[];no_defaults=0
for t in meta['templates']:
 tid=t['identity']['template_id'];old=json.loads((r/f'checkpoints/Metadata_Input_Snapshot/Structured_Shells/{tid}.json').read_text());now=json.loads((r/f'intermediate/Structured_Shells/{tid}.json').read_text());lm=json.loads((r/f'intermediate/DOCX_Locator_Map/{tid}.json').read_text());oldmap=json.loads((r/f'checkpoints/Metadata_Input_Snapshot/DOCX_Locator_Map/{tid}.json').read_text());family=t['identity']['structural_family']
 assert len(old['footnotes'])==len(t['footnotes'])
 for a,b in zip(old['footnotes'],t['footnotes']):assert {k:a[k] for k in physical}=={k:b[k] for k in physical},(tid,a['footnote_id'])
 for key in ['physical_cells','physical_blocks','listing_rows','source_elements','occurrence_relations',family+'_spec']:assert old[key]==now[key],(tid,key)
 for key in ['source_elements','occurrence_relations','docx_boundary']:assert t[key]==lm[key]==oldmap[key],(tid,key)
 assert t[family+'_spec']==old[family+'_spec']
 actual=hashlib.sha256((r/'TFL_Template_Library'/t['identity']['file_path']).read_bytes()).hexdigest();assert actual==t['docx_boundary']['document_sha256']
 assert all(not t['adaptation'][k] for k in ['required_sap_fields','editable_elements','permitted_defaults']);no_defaults+=1
 assert t['quality']['review_status']=='pending';refs={e['ref_id'] for e in t['provenance']['evidence']};assert len(refs)==len(t['provenance']['evidence'])
 for e in t['provenance']['evidence']:
  assert e['document_id']=='SAP_001_11'
  if e['source_record_id']:assert (r/f"source_registry/Source_Records/{e['source_record_id']}.json").exists()
 assert len({s['json_pointer'] for s in t['field_statuses']})==len(t['field_statuses'])
 records.append(dict(template_id=tid,physical_notes_and_scopes='unchanged',native_structures='unchanged',locator_map='identical',actual_docx_sha256='unchanged',footnote_rules=sum(len(f['semantic_rules']) for f in t['footnotes']),quality='pending'))
result=dict(metadata_json_schema='pass',metadata_records_checked=len(records),physical_footnotes=sum(len(t['footnotes']) for t in meta['templates']),semantic_rules=sum(x['footnote_rules'] for x in records),zero_default_templates=no_defaults,all_prior_physical_source_fields='unchanged',all_actual_docx_sha256='unchanged',metadata_map_structure_parity='pass',metadata_scope='source only',approval_granted=False,records=records)
(r/'qa/Metadata_Parity_Check.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='records'},indent=2))
