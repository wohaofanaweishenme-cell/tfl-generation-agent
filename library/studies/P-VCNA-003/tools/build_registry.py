import json,re,shutil,hashlib,collections,zipfile,xml.etree.ElementTree as ET
from pathlib import Path
base=Path.cwd(); work=base/'identification_work';root=base/'Study_P-VCNA-003'
for d in ['original','source_registry/Source_Records','qa','checkpoints/pages','tools']: (root/d).mkdir(parents=True,exist_ok=True)
pages=json.loads((work/'pages.json').read_text());lines=json.loads((work/'lines.json').read_text());did='SAP_001_11';study='P-VCNA-003'
def save(p,x): (root/p).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def region(n,y0=0,y1=None):
 p=pages[n-1];return dict(document_id=did,pdf_page=n,bbox=[0,max(0,y0),p['width'],min(p['height'],y1 if y1 is not None else p['height'])],coordinate_system='pdf_points_top_left')
def ln_y(n,pattern):return next(l['bbox'][1] for l in lines[n-1]['lines'] if re.search(pattern,l['text']))
# Full-page evidence is retained separately from precise shell-owned split regions.
for p in pages:
 (root/f"checkpoints/pages/page_{p['page']:03}.txt").write_text(p['text'])
 shutil.copy2(work/f"pages/page_{p['page']}.png",root/f"checkpoints/pages/page_{p['page']:03}.png")
shutil.copy2(work/'pages.json',root/'checkpoints/PDFKit_Page_Text.json');shutil.copy2(work/'lines.json',root/'checkpoints/PDFKit_Line_Regions.json')
source='SAP_001_11 copy 2.pdf';shutil.copy2(base/source,root/'original'/source)
brief='04_TFL_Content_List_to_Shell_Generation_Agent copy 2.docx';shutil.copy2(base/brief,root/'original'/brief)
src=dict(document_id=did,file_path='original/'+source,kind='sap')
save('Study_Run_Config.json',dict(schema_version='2.4',study_id=study,library_id='SOURCE_P_VCNA_003_v24',sources=[src],shells_inside_sap=True,approved_style_guide_path=None,source_unit_policy='physical_shells_only',expand_content_list_entries=False,notes='Source-only identification. No_style_guide; permitted_defaults=[] for all later metadata. Project brief is supporting project documentation, not clinical evidence. Cover date reads 16ARR2025; no date normalization or correction.'))
save('source_registry/Study_Source_Inventory.json',dict(schema_version='2.4',study_id=study,sources=[dict(**src,format='pdf',sha256=hashlib.sha256((base/source).read_bytes()).hexdigest(),version='Final 3.0')],notes=['Formal study ID P-VCNA-003 verified on cover; Simbec-Orion Study ID 35667.','86 physical PDF pages; printed pages 1-3 and 30-112. Printed pages 4-29 are absent from supplied file, not unreadable pages.','Project brief copied unchanged to original/; not a SAP, shell, or content-list source. Design package is workflow/schema/tooling, not clinical evidence.','PDF text extracted using macOS PDFKit; all page images reviewed in contact sheets for identification, with enlarged inspection of cover and cross-page boundary cases. Fine text and clinical semantics are not fully visually verified.','Appendix study-design diagram on physical page 86 has image text absent from PDF text extraction; it is not a numbered TFL shell.']))
idx=[]
for p in pages:
 m=re.search(r'Page (\d+) of 112',p['text']);idx.append(dict(document_id=did,pdf_page=p['page'],printed_page=m.group(1) if m else None,width_points=p['width'],height_points=p['height'],scan_status='examined',notes='Identification scan: PDFKit text and rendered-page overview examined; not a full-resolution structure or semantic verification.'+(' Appendix diagram image not transcribed; non-TFL.' if p['page']==86 else '')))
save('source_registry/Source_Page_Index.json',dict(schema_version='2.4',pages=idx,docx_source_scan_notes=[]))
# Explicit continuation/panel groups only; no layout-reference expansion.
groups=[]
for p in pages[10:85]:
 m=re.search(r'^(Table|Figure|Listing) ([\d.]+) (.+)$',p['text'],re.M)
 if m:
  key=(m[1],m[2]);found=next((g for g in groups if g['key']==key),None)
  if found:found['pages'].append(p['page']);found['titles'].append(m[3])
  else:groups.append(dict(key=key,pages=[p['page']],titles=[m[3]]))
 else:groups[-1]['pages'].append(p['page'])
shells=[];records={}
for g in groups:
 typ,num=g['key'];ot=typ.lower();tid=('PVCNA003_'+typ[0]+'_'+num.replace('.','_'));regs=[];checks=[];refs=[]
 for n in g['pages']:
  p=pages[n-1];t=p['text'];lo=0;hi=p['height']
  if n==23:lo=ln_y(n,r'^P-VCNA-003 dd')-1
  if n==32:lo=ln_y(n,r'^P-VCNA-003 dd')-1
  regs.append(region(n,lo,hi))
  if lo: t='\n'.join(l['text'] for l in lines[n-1]['lines'] if l['bbox'][1]>=lo)
  checks.append(dict(document_id=did,location=f'PDF physical page {n}; owned region in source_regions; printed page {idx[n-1]["printed_page"]}',text=t,readable=True))
  if re.search(r'Programming [Nn]ote',t):
   note=t[re.search(r'Programming [Nn]ote',t).start():].split('Form STATt004')[0].rstrip()
   refs.append(dict(exact_text=note,source_regions=[region(n,max(lo,ln_y(n,r'Programming [Nn]ote')))],notes='Source programming/layout note only; do not execute referenced adaptations or expand shells.'))
 # Leading content physically continues previous shell, split before next shell header.
 if num=='14.3.1.1':
  n=23;end=ln_y(n,r'^P-VCNA-003 dd')-1;regs.append(region(n,0,end));checks.append(dict(document_id=did,location='PDF physical page 23 leading source/path/page footer, before next shell header',text='\n'.join(l['text'] for l in lines[n-1]['lines'] if l['bbox'][1]<end),readable=True))
 if num=='14.3.4.6':
  n=32;end=ln_y(n,r'^P-VCNA-003 dd')-1;rr=region(n,0,end);regs.append(rr);tx='\n'.join(l['text'] for l in lines[n-1]['lines'] if l['bbox'][1]<end);checks.append(dict(document_id=did,location='PDF physical page 32 leading programming note, before Table 14.3.5.2 header',text=tx,readable=True));refs.append(dict(exact_text=tx.split('Programming Note:',1)[-1].strip(),source_regions=[rr],notes='Continued programming note belongs to Table 14.3.4.6; preserve only as note.'))
 notes=['Original title retained from first panel; all panel titles are retained in text checkpoints.','Regions conservatively retain page wrappers; fine-grained exclusion and structural transcription deferred to stage 2.']
 sh=dict(template_id=tid,output_type=ot,structural_family_candidate='listing' if num in ['14.3.2.1','14.3.3'] else ot,original_tfl_number=num,original_title=g['titles'][0],source_regions=regs,source_docx_locations=[],planned_file_path=f'{ot}/{tid}.docx',status='confirmed',source_reference_notes=refs)
 shells.append(sh);records[tid]=dict(schema_version='2.4',template_id=tid,source_regions=regs,source_docx_locations=[],text_checkpoints=checks,notes=notes)
 save(f'source_registry/Source_Records/{tid}.json',records[tid])
# Embedded source directory: preserve entries independently of shell existence.
entries=[]
for p in pages[3:9]:
 ls=p['text'].splitlines(); starts=[i for i,l in enumerate(ls) if re.match(r'^\*?(Table|Figure|Listing) [\d.]+ ',l)]
 for j,i in enumerate(starts):
  stop=starts[j+1] if j+1<len(starts) else len(ls);chunk=ls[i:stop]
  clean=[]
  for l in chunk:
   if re.match(r'^(Form STAT|14\.\d LIST|Safety Data|PK/PD Data|Efficacy Data)',l):break
   clean.append(l)
  raw='\n'.join(clean);m=re.match(r'^\*?(Table|Figure|Listing) ([\d.]+) (.*)',clean[0]);text=' '.join([m[3]]+clean[1:]);pop=None
  for pat in ['Intent-to-Treat Set','Full Analysis Set','Safety Analysis Set','All Randomized Set','Per Protocol Set','Pharmacodynamic Set']:
   if pat in text:pop=pat;text=text.replace(pat,'').strip();break
  eid=f'CL_{len(entries)+1:03}';entries.append(dict(entry_id=eid,document_id=did,original_tfl_number=m[2],output_type=m[1].lower(),original_title=text,population=pop,source_regions=[region(p['page'])]))
# retain raw directory text and raw row strings separately, preserving stars/order/line wraps.
save('source_registry/Content_List.json',dict(schema_version='2.4',entries=entries))
mappings=[]
for e in entries:
 matches=[s for s in shells if s['output_type']==e['output_type'] and s['original_tfl_number']==e['original_tfl_number']];notes=[]
 for s in shells:
  for ref in s['source_reference_notes']:
   if re.search(r'(?<!\d)'+re.escape(e['original_tfl_number'])+r'(?![\d.])',ref['exact_text']):notes.append(ref)
 reason='Matching source type and number physically displayed; title/population retained separately, including source wording differences.' if matches else ('No independent shell displayed in supplied physical pages 1-86; layout-reference note exists and is preserved only as a note.' if notes else 'No independent shell displayed in supplied physical pages 1-86. No explicit individually numbered layout reference located; range-reference notes remain preserved on their source shells.')
 mappings.append(dict(entry_id=e['entry_id'],source_document_id=did,original_tfl_number=e['original_tfl_number'],original_title=e['original_title'],relation='direct_shell' if matches else 'no_source_shell_found',review_status='verified',template_ids=[s['template_id'] for s in matches],checked_document_ids=[did],reason=reason,source_reference_notes=notes))
save('source_registry/Shell_Manifest.json',dict(schema_version='2.4',study_id=study,shells=shells,content_list_present=True,content_list_mappings=mappings,notes=['Physical shell count is independent of content-list count.','Same-number panels/continuations form one shell only where physically continuous or explicitly instructed in source.','PDF p23 leading footer belongs to previous Table 14.3.1.1; p32 leading note belongs to previous Table 14.3.4.6.','Content-list mappings verified for physical source presence/absence only; no human approval or clinical validation implied.','Appendix 16.1 Study Design is a study-design diagram, not a TFL shell.']))
issues=[]
def issue(cat,desc,reg=[],sev='warning'):issues.append(dict(issue_id=f'ID_{len(issues)+1:03}',template_id=None,severity=sev,category=cat,description=desc,status='open',source_regions=reg))
issue('supplied_file_gap','Printed pages 4-29 absent from supplied 86-page PDF. Identification conclusions are restricted to actual supplied file; missing SAP body cannot support later semantic interpretation.')
issue('non_text_region','Physical page 86 contains an image-based study-design diagram not transcribed by PDFKit. Visually seen in overview; detailed image content remains unverified. Not a TFL shell.',[region(86)])
issue('visual_verification_scope','All 86 pages examined via extracted text and rendered overviews; full-resolution verification of every text region, footnote and table cell is not_run and belongs to subsequent extraction/QA. Source text checkpoints are parser output, not certified verbatim transcription.')
issue('source_inconsistency','Figure 14.2.1 programming note refers to Figure 14.2.6 as Duration of Response, while directory calls 14.2.6 Progression Free Survival. Preserve both; do not correct.',[region(41)])
issue('source_title_variation','Directory uses Demographic for Listing 16.2.4.1, physical shell uses Demographics; table directory uses Demographics whereas Table 14.1.2.1 shell uses Demographic. Same type/number presence mapping retained; no wording normalization.',[region(8),region(55),region(4),region(12)])
issue('unapproved_style_guide','No approved style guide supplied. Source p10 formatting instructions remain source evidence only. Future permitted_defaults=[].',[region(10)],'info')
save('source_registry/Mapping_Issues.json',dict(schema_version='2.4',stage='identification',issues=issues))
ids=[s['template_id'] for s in shells]
save('qa/Extraction_Progress.json',dict(schema_version='2.4',study_id=study,stage='identification',manifest_ids=ids,completed_ids=ids,remaining_ids=[],blocked_ids=[],identification_complete=True,full_study_complete=False,notes=['Identification completed for the supplied 86 physical pages, not for absent original-document pages.','Source identification only; stage 2-5 not executed. Visual/semantic final QA not_run; approval pending.','Required package validator attempted separately; see validation logs for dependency limitations.']))
counts=dict(collections.Counter(s['output_type'] for s in shells));clcounts=dict(collections.Counter(e['output_type'] for e in entries));rel=dict(collections.Counter(m['relation'] for m in mappings))
save('qa/Identification_Summary.json',dict(study_id=study,physical_pdf_pages=86,examined_pages=86,physical_shell_counts=counts,physical_shell_total=len(shells),content_list_counts=clcounts,content_list_total=len(entries),mapping_counts=rel,docx_created=0,approved=False,permitted_defaults=[],scan_gaps=['Printed pages 4-29 absent in input','Appendix diagram image text not transcribed','Fine-grained full-resolution visual/semantic verification not_run']))
# Supporting brief object locations, without invented PDF pages.
with zipfile.ZipFile(base/brief) as z:
 ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'};r=ET.fromstring(z.read('word/document.xml'));pars=[{'location':f'word/document.xml/body/p[{i}]','text':''.join(n.text or '' for n in p.findall('.//w:t',ns))} for i,p in enumerate(r.findall('w:body/w:p',ns),1)]
 save('checkpoints/Project_Brief_Scan.json',dict(file_path='original/'+brief,role='project_requirements_not_clinical_source',sha256=hashlib.sha256((base/brief).read_bytes()).hexdigest(),paragraphs=pars,table_count=len(r.findall('.//w:tbl',ns)),notes='Native paragraph text read; not a source shell document. No fabricated PDF page locations.'))
for f in (work/'tools').glob('*'):shutil.copy2(f,root/'tools'/f.name)
print(json.dumps(dict(shells=counts,total=len(shells),content_list=clcounts,total_entries=len(entries),mappings=rel),indent=2))
