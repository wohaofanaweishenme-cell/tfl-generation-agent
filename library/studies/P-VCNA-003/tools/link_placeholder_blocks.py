import json
from pathlib import Path
r=Path(__file__).resolve().parents[1];evidence=json.loads((r/'checkpoints/Source_Region_Evidence.json').read_text())['evidence']
for p in (r/'intermediate/Structured_Shells').glob('*.json'):
 s=json.loads(p.read_text())
 for el in s['source_elements']:
  if el['element_type']!='placeholder':continue
  ref=evidence[el['occurrences'][0]['source_ref_ids'][0]]['source_regions'][0];bb=ref['bbox'];candidates=[]
  for b in s['physical_blocks']:
   br=b['source_regions'][0];q=br['bbox']
   if br['pdf_page']==ref['pdf_page'] and q[0]-.1<=bb[0] and q[1]-.1<=bb[1] and bb[2]<=q[2]+.1 and bb[3]<=q[3]+.1:candidates.append(b)
  if candidates:
   b=min(candidates,key=lambda b:(b['source_regions'][0]['bbox'][2]-b['source_regions'][0]['bbox'][0])*(b['source_regions'][0]['bbox'][3]-b['source_regions'][0]['bbox'][1]))
   if el['element_id'] not in b['source_element_ids']:b['source_element_ids'].append(el['element_id'])
 p.write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n')
