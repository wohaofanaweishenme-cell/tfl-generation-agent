import json,re
from pathlib import Path
r=Path(__file__).resolve().parents[1];cp=r/'qa/Corrections_Log.json';log=json.loads(cp.read_text()) if cp.exists() else dict(schema_version='2.4',corrections=[])
for sh in json.loads((r/'source_registry/Shell_Manifest.json').read_text())['shells']:
 p=r/f"intermediate/Structured_Shells/{sh['template_id']}.json";s=json.loads(p.read_text());changed=False
 for b in s['physical_blocks']:
  m=re.match(r'^(Table|Figure|Listing) ([\d.]+)',b['exact_text'] or '')
  if b['kind']=='title' and m and m[2]!=sh['original_tfl_number']:
   b['kind']='programming_note';b['notes']='Continuation of source Programming Note; cited output is a layout reference, not a shell title.'
   for e in s['source_elements']:
    if e['element_id'] in b['source_element_ids']:
     e['element_type']='programming_note'
     for o in e['occurrences']:o['role']='programming_note'
   s['programming_notes'].append(dict(exact_text=b['exact_text'],source_regions=b['source_regions'],notes=b['notes']))
   s['programming_notes'].sort(key=lambda x:(x['source_regions'][0]['pdf_page'],x['source_regions'][0]['bbox'][1]))
   log['corrections'].append(dict(correction_id=f'CORR_{len(log["corrections"])+1:03}',template_id=sh['template_id'],reason='Rendered-source comparison identified a source programming-note continuation misclassified as a title. Corrected block/element role only; original text and reference retained, no source shell created.',changed_paths=[str(p.relative_to(r)),f"TFL_Template_Library/{sh['planned_file_path']}",f"intermediate/DOCX_Locator_Map/{sh['template_id']}.json"],source_basis=[dict(exact_text=b['exact_text'],source_regions=b['source_regions'],notes='Visually within source Programming Note on the supplied SAP page.')],checks_to_rerun=['DOCX rebuild and hash update','actual bookmark scopes/source text','render and visual comparison','static validator --stage docx']))
   changed=True
 if changed:p.write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n')
cp.write_text(json.dumps(log,ensure_ascii=False,indent=2)+'\n')
