"""Fresh original-PDF character audit; not a clinical or visual approval."""
import json,unicodedata,collections,hashlib,zipfile,xml.etree.ElementTree as ET
from pathlib import Path
import pdfplumber
r=Path(__file__).resolve().parents[1]
def read(p):return json.loads((r/p).read_text())
def save(p,x):(r/p).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def chars(s):return collections.Counter(c for c in unicodedata.normalize('NFKC',s or '') if not c.isspace() and c not in '\u00ad\u200b')
m=read('source_registry/Shell_Manifest.json');meta={t['identity']['template_id']:t for t in read('Study_Metadata.json')['templates']};ev=read('checkpoints/Source_Region_Evidence.json')['evidence'];inv=read('source_registry/Study_Source_Inventory.json')
with pdfplumber.open(r/inv['sources'][0]['file_path']) as pdf: pages=[list(p.chars) for p in pdf.pages]
def source(regions):
 out=[]
 for reg in regions:
  a,b,c,d=reg['bbox'];out.extend(ch['text'] for ch in pages[reg['pdf_page']-1] if a-.1<=ch['x0']<c-.1 and b-.1<=ch['top']<d-.1)
 return ''.join(out)
records=[];mismatches=[];fnrecords=[];blanks=0
for sh in m['shells']:
 tid=sh['template_id'];s=read(f'intermediate/Structured_Shells/{tid}.json');t=meta[tid];mp=read(f'intermediate/DOCX_Locator_Map/{tid}.json');local=[]
 for block in s['physical_blocks']:
  original=source(block['source_regions']);a=chars(original);b=chars(block['exact_text'])
  if a!=b:local.append(dict(kind='physical_block',id=block['block_id'],missing=dict(a-b),extra=dict(b-a),source_regions=block['source_regions']))
 for cell in s['physical_cells']:
  if cell['is_blank']:
   blanks+=1;original=source(cell['source_regions'])
   if chars(original):local.append(dict(kind='blank_cell',id=cell['cell_id'],source_text=original,source_regions=cell['source_regions']))
 for f in s['footnotes']:
  regions=[reg for ref in f['evidence_ref_ids'] for reg in ev[ref]['source_regions']];a=chars(source(regions));b=chars(f['exact_text']);equal=a==b
  fnrecords.append(dict(template_id=tid,footnote_id=f['footnote_id'],source_character_multiset='pass' if equal else 'needs_review',source_regions=regions,marker=f['marker'],display_order=f['display_order'],semantic_scope='needs_review' if any(x['mapping_status'] in ['unresolved','inferred'] for x in f['applies_to_refs']) else 'explicit',rule_count=len(f['semantic_rules'])))
  if not equal:local.append(dict(kind='footnote',id=f['footnote_id'],missing=dict(a-b),extra=dict(b-a),source_regions=regions))
 assert t['source_elements']==mp['source_elements']==s['source_elements']
 records.append(dict(template_id=tid,physical_blocks_checked=len(s['physical_blocks']),blank_cells_checked=sum(c['is_blank'] for c in s['physical_cells']),footnotes_checked=len(s['footnotes']),candidate_differences=len(local)))
 mismatches.extend(dict(template_id=tid,**x) for x in local)
save('qa/Fresh_Source_Character_Audit.json',dict(method='Fresh pdfplumber read of original PDF bytes; glyph selection by persisted source bounding boxes. NFKC non-whitespace character multisets. Order, superscripts and semantic scope are NOT proven. Candidate differences require original-image inspection.',source_sha256=hashlib.sha256((r/inv['sources'][0]['file_path']).read_bytes()).hexdigest(),pages_read=len(pages),blank_cells_checked=blanks,records=records,candidate_differences=mismatches))
save('qa/Footnote_Cross_Layer_Checks.json',dict(scope='Fresh original PDF character check plus persisted physical note records. Typography and semantic scope need independent review; no approval.',physical_footnotes=len(fnrecords),records=fnrecords))
print(json.dumps(dict(pages=len(pages),templates=len(records),blanks=blanks,differences=len(mismatches),difference_kinds=dict(collections.Counter(x['kind'] for x in mismatches)),examples=mismatches[:5]),ensure_ascii=False,indent=2))
