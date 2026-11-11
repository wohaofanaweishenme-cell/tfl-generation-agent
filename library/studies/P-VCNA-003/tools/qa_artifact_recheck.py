"""Read actual DOCX XML and persisted IDs; detailed per-occurrence structural evidence."""
import json,hashlib,zipfile,unicodedata,xml.etree.ElementTree as ET
from pathlib import Path
r=Path(__file__).resolve().parents[1];W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
def read(p):return json.loads((r/p).read_text())
def norm(s):return ' '.join(unicodedata.normalize('NFKC',s or '').split())
def save(p,x):(r/p).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
meta=read('Study_Metadata.json');details=[];records=[]
for t in meta['templates']:
 tid=t['identity']['template_id'];s=read(f'intermediate/Structured_Shells/{tid}.json');mp=read(f'intermediate/DOCX_Locator_Map/{tid}.json');path=r/'TFL_Template_Library'/mp['file_path'];fam=s['structural_family'];sp=s[fam+'_spec'];rows={x['id'] for x in sp.get('rows',[])}|{x['id'] for x in s['listing_rows']};cols={x['id'] for x in sp.get('columns',[])};panels={x['panel_id'] for x in sp.get('panels',[])};els={x['element_id'] for x in s['source_elements']}
 for b in s['physical_blocks']:assert set(b['source_element_ids'])<=els,(tid,b['block_id'])
 for c in s['physical_cells']:assert c['row_id'] in rows and c['column_id'] in cols and c['panel_id'] in panels,(tid,c['cell_id'])
 with zipfile.ZipFile(path) as z:assert z.testzip() is None;xml=ET.fromstring(z.read('word/document.xml'))
 seq=list(xml.iter());starts={};ends={}
 for i,n in enumerate(seq):
  if n.tag==W+'bookmarkStart':
   name=n.attrib[W+'name'];bid=n.attrib[W+'id'];assert name not in starts;assert bid not in [x[1] for x in starts.values()];starts[name]=(i,bid)
  if n.tag==W+'bookmarkEnd':assert n.attrib[W+'id'] not in ends;ends[n.attrib[W+'id']]=i
 def bounds(name):
  a,bid=starts[name];return a,ends[bid]
 boundary=mp['docx_boundary'];a,ae=bounds(boundary['start_marker']);b,be=bounds(boundary['end_marker']);assert ae<b
 sha=hashlib.sha256(path.read_bytes()).hexdigest();assert sha==boundary['document_sha256'];assert mp['source_elements']==s['source_elements']==t['source_elements'];assert t['docx_boundary']==boundary
 checked=excluded=0
 for e in mp['source_elements']:
  for o in e['occurrences']:
   if o['docx_locator'] is None:
    excluded+=1;details.append(dict(template_id=tid,element_id=e['element_id'],occurrence_id=o['occurrence_id'],panel_id=o['panel_id'],role=o['role'],status='needs_review',reason='Explicit wrapper exclusion; no bookmark claimed. Original retained.'));continue
   x,y=bounds(o['docx_locator'].split(':',1)[1]);assert ae<x<y<b
   text=''.join((n.text or '') if n.tag==W+'t' else '\n' if n.tag in [W+'br',W+'tab'] else '' for n in seq[x+1:y]);assert norm(text)==norm(o['source_text']),(tid,o['occurrence_id'])
   checked+=1;details.append(dict(template_id=tid,element_id=e['element_id'],occurrence_id=o['occurrence_id'],panel_id=o['panel_id'],role=o['role'],source_text=o['source_text'],actual_bookmark_text=text,docx_locator=o['docx_locator'],source_ref_ids=o['source_ref_ids'],status='pass',scope='Actual XML text/order/containment only; panel label agrees with source structure, not independent clinical confirmation.'))
 records.append(dict(template_id=tid,sha256=sha,boundary='pass',physical_block_element_references='pass',physical_cell_row_column_panel_references='pass',metadata_map_structure='identical',occurrences_checked=checked,documented_wrapper_exclusions=excluded))
save('qa/Actual_DOCX_Occurrence_Checks.json',dict(scope='Fresh actual ZIP/XML checks. Structural only, not semantic/visual approval.',records=records,occurrences=details));print(json.dumps(dict(templates=len(records),verified=sum(x['occurrences_checked'] for x in records),excluded=sum(x['documented_wrapper_exclusions'] for x in records))))
