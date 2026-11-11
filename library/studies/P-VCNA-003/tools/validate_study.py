#!/usr/bin/env python3
"""Read-only structural validation. Does not approve or perform visual/clinical review."""
import argparse, collections, hashlib, json, pathlib, re, sys, unicodedata, zipfile
from xml.etree import ElementTree as ET
from jsonschema import Draft202012Validator
from docx import Document
from pypdf import PdfReader
V='2.4';W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
STAGES=['identification','structure','docx','metadata','qa']
def norm(t):return re.sub(r'\s+',' ',unicodedata.normalize('NFKC',t)).strip()
def pointer(x,p):
 if p=='':return x
 if not p.startswith('/'):raise ValueError('not a JSON Pointer')
 for k in p[1:].split('/'):
  k=k.replace('~1','/').replace('~0','~');x=x[int(k)] if isinstance(x,list) else x[k]
 return x
class Validator:
 def __init__(self,root,stage,package_root=None):
  self.root=pathlib.Path(root).resolve();self.stage=STAGES.index(stage);self.pack=pathlib.Path(package_root or pathlib.Path(__file__).resolve().parents[1]);self.errors=[];self.warnings=[];self.checks=[];self.documents={};self.structures={};self.maps={};self.docs={}
 def err(self,code,detail):self.errors.append({'code':code,'detail':str(detail)})
 def warn(self,code,detail):self.warnings.append({'code':code,'detail':str(detail)})
 def path(self,p,base=None):
  b=pathlib.Path(base or self.root).resolve();q=(b/p).resolve()
  if pathlib.Path(p).is_absolute() or not q.is_relative_to(b):raise ValueError('Unsafe or escaping relative path: '+str(p))
  return q
 def read(self,p,schema,required=True):
  try:
   f=self.path(p)
   if not f.exists():
    if required:self.err('missing_file',p)
    return None
   x=json.loads(f.read_text());s=json.loads((self.pack/'schemas'/f'{schema}.schema.json').read_text())
   errs=list(Draft202012Validator(s).iter_errors(x))
   for e in errs:self.err('schema',f'{p} /'+ '/'.join(map(str,e.path))+': '+e.message)
   return None if errs else x
  except Exception as e:self.err('read_or_schema',f'{p}: {e}');return None
 def unique(self,seq,key,where):
  vals=[x[key] if isinstance(x,dict) else x for x in seq]
  if len(vals)!=len(set(vals)):self.err('duplicate_id',where)
  return set(vals)
 def regions(self,regions,where):
  for r in regions:
   d=self.documents.get(r['document_id'])
   if d is None:self.err('source_reference',where+': unknown document');continue
   if d['format']!='pdf':self.err('source_region',where+': PDF bbox used on non-PDF source');continue
   n=r['pdf_page'];pages=d.get('_pages',[])
   if not 1<=n<=len(pages):self.err('source_page',where+': outside actual PDF');continue
   x0,y0,x1,y1=r['bbox'];ww,hh=pages[n-1]
   if not (0<=x0<x1<=ww+.05 and 0<=y0<y1<=hh+.05):self.err('source_bbox',where+': invalid dimensions')
 def occurrences(self,t,where,metadata=False):
  elements=t.get('source_elements',[]);eids=self.unique(elements,'element_id',where+'/elements');occ=[o for e in elements for o in e['occurrences']];oids=self.unique(occ,'occurrence_id',where+'/occurrences');lookup={o['occurrence_id']:o for o in occ}
  if not elements:self.warn('empty_coverage',where+': no source elements recorded')
  for rel in t.get('occurrence_relations',[]):
   a,b=rel['from_occurrence_id'],rel['to_occurrence_id']
   if a not in oids or b not in oids or a==b:self.err('occurrence_relation',where+': dangling/self relation')
   elif rel['relation_type']=='exact_repeat' and lookup[a]['source_text']!=lookup[b]['source_text']:self.err('exact_repeat',where+': source texts differ')
  self.unique(t.get('occurrence_relations',[]),'relation_id',where+'/relations')
  for o in occ:
   if o['verification_status']!='verified' or o['source_text'] is None:self.warn('occurrence_review',where+': '+o['occurrence_id'])
  if metadata:
   evidence=t['provenance']['evidence'];refs=self.unique(evidence,'ref_id',where+'/evidence')
   for e in evidence:
    if e['document_kind'] in ['source_shell','sap_body'] and e['document_id'] not in self.documents:self.err('document_reference',where+': '+e['document_id'])
    regions=[dict(r,document_id=e['document_id']) for r in e.get('source_regions',[])];self.regions(regions,where)
    doc=self.documents.get(e['document_id']);pages=doc.get('_pages') if doc else None
    if pages is not None and any(n<1 or n>len(pages) for n in e['page_numbers']):self.err('evidence_page',where)
   def checkrefs(ids,label):
    if not set(ids)<=refs:self.err('evidence_reference',where+': '+label)
   for e in elements:
    if e['metadata_pointer'] is not None:
     try:pointer(t,e['metadata_pointer'])
     except Exception:self.err('pointer',where+': '+e['metadata_pointer'])
    for o in e['occurrences']:checkrefs(o['source_ref_ids'],o['occurrence_id'])
   for rel in t['occurrence_relations']:checkrefs(rel['source_ref_ids'],rel['relation_id'])
   for x in [*t['provenance']['field_links'],*t['field_statuses'],*t['issues']]:
    try:pointer(t,x['json_pointer'])
    except Exception:self.err('pointer',where+': '+x['json_pointer'])
    checkrefs(x.get('ref_ids',x.get('evidence_ref_ids',x.get('source_ref_ids',[]))),'field')
   for a in t['adaptation']['editable_elements']:
    if a['source_element_id'] not in eids:self.err('adaptation_reference',where)
   for default in t['adaptation']['permitted_defaults']:
    matches=[e for e in evidence if e['ref_id']==default['basis_ref_id'] and e['document_kind']=='style_guide']
    if not matches:self.err('default_evidence',where)
   for f in t['footnotes']:
    checkrefs(f['evidence_ref_ids'],f['footnote_id'])
    for rule in f['semantic_rules']:checkrefs(rule['evidence_ref_ids'],rule['rule_id'])
    candidates=[e for e in elements if e['metadata_pointer'] in [f'/footnotes/{t["footnotes"].index(f)}',f'/footnotes/{t["footnotes"].index(f)}/exact_text']]
    if not candidates:self.err('footnote_occurrence',where+': '+f['footnote_id'])
    elif not any(o['source_text']==f['exact_text'] for e in candidates for o in e['occurrences']):self.err('footnote_text',where+': '+f['footnote_id'])
   self.spec_refs(t,where)
  return occ
 def spec_refs(self,t,where):
  tid=t.get('identity',{}).get('template_id',t.get('template_id'));family=t.get('identity',{}).get('structural_family',t.get('structural_family'));spec=t.get(str(family)+'_spec',{});rows=spec.get('rows',[]);cols=spec.get('columns',[])
  rids=self.unique(rows,'id',where+'/rows');cids=self.unique(cols,'id',where+'/columns');panels=spec.get('panels',[]);pids=self.unique(panels,'panel_id',where+'/panels')
  if family=='listing':rids|={r['id'] for r in self.structures.get(tid,t).get('listing_rows',[])}
  for nodes in [rows,cols]:
   by={x['id']:x for x in nodes}
   for x in nodes:
    seen=set();current=x
    while current.get('parent_id') is not None:
     pid=current['parent_id']
     if pid not in by or pid in seen:self.err('hierarchy',where);break
     seen.add(pid);current=by[pid]
  for panel in panels:
   if not set(panel.get('row_ids',[]))<=rids or not set(panel.get('column_ids',[]))<=cids:self.err('panel_reference',where)
  for e in t.get('source_elements',[]):
   for o in e['occurrences']:
    if o['panel_id'] is not None and o['panel_id'] not in pids:self.err('occurrence_panel',where)
  for rule in spec.get('cell_rules',[]):
   if rule['row_id'] not in rids or rule['column_id'] not in cids:self.err('cell_rule',where)
  fids=self.unique(t.get('footnotes',[]),'footnote_id',where+'/footnotes');rules=[r for f in t.get('footnotes',[]) for r in f['semantic_rules']];self.unique(rules,'rule_id',where+'/rules')
  for f in t.get('footnotes',[]):
   for ref in [*f['applies_to_refs'],*[x for r in f['semantic_rules'] for x in r.get('applies_to_refs',[])]]:
    kind,x=ref['target_type'],ref['target_id'];valid=True
    if ref['panel_id'] is not None and ref['panel_id'] not in pids:valid=False
    if kind=='row':valid &= x in rids
    elif kind=='column':valid &= x in cids
    elif kind=='panel':valid &= x in pids
    elif kind=='cell':valid &= isinstance(x,str) and ':' in x and x.split(':',1)[0] in rids and x.split(':',1)[1] in cids
    elif kind=='figure_axis':valid &= isinstance(x,str) and ':' in x and x.rsplit(':',1)[0] in pids and x.rsplit(':',1)[1] in ['x','y']
    elif kind=='figure_legend':valid &= x in {e['element_id'] for e in t.get('source_elements',[])}
    elif kind in ['shell','unknown']:valid &= x is None
    if not valid:self.err('footnote_scope',where+': '+f['footnote_id'])
 def docx(self,t,tid):
  try:
   path=self.path(t['file_path'],self.root/'TFL_Template_Library');Document(path)
   with zipfile.ZipFile(path) as z:
    if z.testzip() is not None:raise ValueError('corrupt zip member')
    xml=ET.fromstring(z.read('word/document.xml'))
   seq=list(xml.iter());starts=collections.defaultdict(list);ends=collections.defaultdict(list);names={}
   for i,n in enumerate(seq):
    if n.tag==W+'bookmarkStart':starts[n.attrib[W+'name']].append((i,n.attrib[W+'id']));names[n.attrib[W+'id']]=n.attrib[W+'name']
    elif n.tag==W+'bookmarkEnd':ends[n.attrib[W+'id']].append(i)
   if any(len(v)!=1 for v in starts.values()) or len(names)!=sum(len(v) for v in starts.values()):raise ValueError('duplicate bookmark name or ID')
   def bounds(name):
    pairs=starts.get(name,[])
    if len(pairs)!=1:raise ValueError('missing or repeated bookmark '+name)
    a,bid=pairs[0];end=ends.get(bid,[])
    if len(end)!=1 or end[0]<=a:raise ValueError('unpaired/reversed bookmark '+name)
    return a,end[0]
   b=t['docx_boundary'];a,ae=bounds(b['start_marker']);z,ze=bounds(b['end_marker'])
   if b['start_marker']==b['end_marker'] or ae>=z:raise ValueError('reversed/overlapping shell boundary')
   if hashlib.sha256(path.read_bytes()).hexdigest()!=b['document_sha256']:raise ValueError('DOCX hash mismatch')
   if any(n.tag==W+'t' and (n.text or '').strip() for n in seq[a+1:ae]+seq[z+1:ze]):raise ValueError('boundary bookmarks must be collapsed')
   for o in self.occurrences(t,tid):
    loc=o['docx_locator']
    if loc is None:continue
    if not loc.startswith('bookmark:'):
     if o['verification_status']=='verified':self.err('locator_type',tid+': unsupported verified locator')
     else:self.warn('locator_type',tid+': locator needs external inspection')
     continue
    try:
     aa,bb=bounds(loc.split(':',1)[1])
     if not ae<aa<bb<z:raise ValueError('occurrence outside shell boundary')
     text=''.join(n.text or '' if n.tag==W+'t' else '\n' if n.tag in [W+'br',W+'tab'] else '' for n in seq[aa+1:bb])
     if o['source_text'] is not None and norm(text)!=norm(o['source_text']):raise ValueError('occurrence source_text differs from bookmark text')
    except Exception as e:self.err('occurrence_scope',tid+': '+o['occurrence_id']+': '+str(e))
   if b['verification_status']!='verified':self.warn('boundary_pending',tid)
   self.docs[tid]=path
  except Exception as e:self.err('docx',tid+': '+str(e))
 def run(self):
  cfg=self.read('Study_Run_Config.json','Study_Run_Config');inv=self.read('source_registry/Study_Source_Inventory.json','Study_Source_Inventory');idx=self.read('source_registry/Source_Page_Index.json','Source_Page_Index');man=self.read('source_registry/Shell_Manifest.json','Shell_Manifest');prog=self.read('qa/Extraction_Progress.json','Extraction_Progress')
  if any(x is None for x in [cfg,inv,idx,man,prog]):return self.result()
  logs=[('source_registry/Mapping_Issues.json','identification'),('qa/Extraction_Issues.json','structure'),('qa/DOCX_Generation_Issues.json','docx'),('qa/Metadata_Issues.json','metadata')]
  for path,level in logs:
   if self.stage>=STAGES.index(level):self.read(path,'Issues_Log')
  if self.stage>=4:
   self.read('qa/Corrections_Log.json','Corrections_Log');self.read('qa/Source_Locator_Checks.json','Source_Locator_Checks')
  if any(x['study_id']!=cfg['study_id'] for x in [inv,man,prog]):self.err('study_id','Config/inventory/manifest/progress disagree')
  self.unique(inv['sources'],'document_id','sources');self.unique(cfg['sources'],'document_id','config sources')
  if {x['document_id'] for x in inv['sources']}!={x['document_id'] for x in cfg['sources']}:self.err('source_inventory','source IDs differ')
  for c in cfg['sources']:
   match=next((x for x in inv['sources'] if x['document_id']==c['document_id']),None)
   if match and any(c[k]!=match[k] for k in ['file_path','kind']):self.err('source_config_parity',c['document_id'])
  for src in inv['sources']:
   self.documents[src['document_id']]=src
   try:
    f=self.path(src['file_path'])
    if hashlib.sha256(f.read_bytes()).hexdigest()!=src['sha256']:raise ValueError('source hash mismatch')
    if src['format']=='pdf':src['_pages']=[(float(p.mediabox.width),float(p.mediabox.height)) for p in PdfReader(f).pages]
    else:Document(f)
   except Exception as e:self.err('source_file',src['document_id']+': '+str(e))
  pagekeys=set()
  for p in idx['pages']:
   key=(p['document_id'],p['pdf_page'])
   if key in pagekeys:self.err('duplicate_page',key)
   pagekeys.add(key);self.regions([{'document_id':p['document_id'],'pdf_page':p['pdf_page'],'bbox':[0,0,p['width_points'],p['height_points']]}],'page index')
   if p['scan_status']!='examined':self.warn('scan_gap',key)
  if prog['identification_complete']:
   for did,d in self.documents.items():
    for n in range(1,len(d.get('_pages',[]))+1):
     if (did,n) not in pagekeys:self.err('scan_coverage',f'{did} page {n} absent')
  ids=self.unique(man['shells'],'template_id','manifest');by={s['template_id']:s for s in man['shells']}
  if not ids:self.warn('no_real_shells','No actual shell has been registered; do not generate invented outputs.')
  if set(prog['manifest_ids'])!=ids:self.err('progress','manifest ID set differs')
  sets=[set(prog[k]) for k in ['completed_ids','remaining_ids','blocked_ids']]
  if set.union(*sets)!=ids or any(sets[i]&sets[j] for i in range(3) for j in range(i+1,3)):self.err('progress','completed/remaining/blocked must partition manifest IDs')
  if prog['full_study_complete'] and (sets[1] or sets[2] or not prog['identification_complete'] or prog['stage']!='qa'):self.err('completion','invalid full completion claim')
  self.unique(man['content_list_mappings'],'entry_id','content mappings')
  cl=self.read('source_registry/Content_List.json','Content_List',man['content_list_present'])
  if cl is not None:
   clids=self.unique(cl['entries'],'entry_id','content entries')
   if clids!={m['entry_id'] for m in man['content_list_mappings']}:self.err('content_coverage','directory mapping coverage differs')
  elif man['content_list_mappings']:self.err('content_presence','mappings without Content List')
  for m in man['content_list_mappings']:
   if not set(m['template_ids'])<=ids:self.err('mapping_reference',m['entry_id'])
   if m['relation']=='direct_shell' and not m['template_ids']:self.err('mapping_relation',m['entry_id'])
  for sh in man['shells']:
   tid=sh['template_id'];self.regions(sh['source_regions'],tid)
   if not sh['source_regions'] and not sh['source_docx_locations']:self.err('source_location',tid)
   for dl in sh['source_docx_locations']:
    if dl['document_id'] not in self.documents:self.err('source_reference',tid)
   if pathlib.PurePosixPath(sh['planned_file_path']).parts[:1]!=(sh['output_type'],) or not sh['planned_file_path'].endswith('.docx'):self.err('type_path',tid)
   sr=self.read(f'source_registry/Source_Records/{tid}.json','Source_Record')
   if sr:
    if sr['template_id']!=tid:self.err('source_record_id',tid)
    self.regions(sr['source_regions'],tid)
   for folder,schema in [('intermediate/Structured_Shells','Structured_Shell'),('intermediate/DOCX_Locator_Map','DOCX_Locator_Map')]:
    level=1 if schema=='Structured_Shell' else 2
    if self.stage<level:continue
    f=f'{folder}/{tid}.json';required=tid in sets[0];data=self.read(f,schema,required)
    if data is None:continue
    if data['template_id']!=tid:self.err('template_identity',f)
    if schema=='Structured_Shell':self.structures[tid]=data;self.regions(data['source_regions'],tid);self.occurrences(data,tid);self.spec_refs(data,tid)
    else:self.maps[tid]=data;self.docx(data,tid)
  if self.stage>=2:
   library=self.root/'TFL_Template_Library'
   expected={x['planned_file_path'] for x in man['shells']}
   for docfile in library.rglob('*.docx'):
    relative=docfile.relative_to(library).as_posix()
    if relative not in expected:self.err('extra_docx','Unregistered output: '+relative)
    elif docfile.resolve() not in set(self.docs.values()):self.err('unvalidated_docx',relative)
  metadata=self.read('Study_Metadata.json','Template_Metadata',self.stage>=3) if self.stage>=3 else None
  if metadata is not None:
   if metadata['library_id']!=cfg['library_id']:self.err('library_id','metadata/config differ')
   mids=self.unique(metadata['templates'],'template_id','metadata') if False else [t['identity']['template_id'] for t in metadata['templates']]
   if len(mids)!=len(set(mids)) or not set(mids)<=ids:self.err('metadata_ids','duplicate/unknown IDs')
   if not sets[0]<=set(mids):self.err('metadata_coverage','completed IDs missing metadata')
   for t in metadata['templates']:
    tid=t['identity']['template_id'];self.occurrences(t,tid,True)
    if tid not in by:continue
    sh=by[tid]
    if t['source']['study_id']!=cfg['study_id']:self.err('study_id',tid)
    if t['adaptation']['permitted_defaults'] and not cfg['approved_style_guide_path']:self.err('unapproved_defaults',tid)
    for key,sk in [('file_path','planned_file_path'),('output_type','output_type'),('original_title','original_title'),('original_tfl_number','original_tfl_number')]:
     if t['identity'][key]!=sh[sk]:self.err('identity_mismatch',tid+': '+key)
    lm=self.maps.get(tid);st=self.structures.get(tid)
    if lm:
     for key in ['source_elements','occurrence_relations','docx_boundary']:
      if lm[key]!=t[key]:self.err('locator_map_parity',tid+': '+key)
    if st:
     family=t['identity']['structural_family']
     for key in [family+'_spec','source_elements','occurrence_relations']:
      if st.get(key)!=t.get(key):self.err('structure_parity',tid+': '+key)
     physical_keys=['footnote_id','marker','exact_text','display_order','applies_to_refs']
     if [{k:f[k] for k in physical_keys} for f in st['footnotes']] != [{k:f[k] for k in physical_keys} for f in t['footnotes']]:self.err('structure_parity',tid+': physical footnotes')
  qa=self.read('qa/Study_QA_Report.json','Study_QA_Report',self.stage>=4) if self.stage>=4 else None
  if qa is not None:
   actual={'physical_shells':len(ids),'structured_records':len(self.structures),'docx_files':len(self.docs),'metadata_records':len(metadata['templates']) if metadata else 0,'approved_records':sum(t['quality']['review_status']=='approved' for t in (metadata or {}).get('templates',[])),'remaining_shells':len(sets[1]|sets[2])}
   if qa['counts']!=actual:self.err('qa_counts',f'actual counts: {actual}')
   if qa['full_study_complete']!=prog['full_study_complete']:self.err('completion','QA/progress disagree')
   approvals={a['template_id']:a for a in qa['human_approvals']}
   for t in (metadata or {}).get('templates',[]):
    tid=t['identity']['template_id']
    for layer in ['visual','semantic']:
     checks=[c for c in qa['checks'] if c['template_id']==tid and c['layer']==layer]
     if not checks or any(c['status']!='pass' for c in checks):self.warn('review_not_passed',tid+': '+layer)
    if t['quality']['review_status']=='approved':
     if tid not in approvals:self.err('approval_record',tid)
     else:
      try:
       if not self.path(approvals[tid]['record_path']).is_file():raise ValueError('missing human record')
      except Exception as e:self.err('approval_record',tid+': '+str(e))
     if any(i['status']=='open' for i in t['issues']):self.err('approval_open_issues',tid)
   for c in qa['checks']:
    for path in c['evidence_paths']:
     try:
      if not self.path(path).exists():self.err('qa_evidence',path)
     except Exception as e:self.err('qa_evidence',e)
  return self.result()
 def result(self):return {'schema_version':V,'validator_scope':'Static contracts, references, actual file/hash/bookmark checks only; no visual/clinical approval or generic PDF extraction.','stage':STAGES[self.stage],'static_result':'fail' if self.errors else 'pass_with_review_warnings' if self.warnings else 'pass','errors':self.errors,'warnings':self.warnings,'counts':{'structured_records_checked':len(self.structures),'docx_files_checked':len(self.docs)},'approval_granted':False}
def main():
 p=argparse.ArgumentParser();p.add_argument('--study-root',required=True);p.add_argument('--stage',choices=STAGES,default='qa');p.add_argument('--report');a=p.parse_args();report=Validator(a.study_root,a.stage).run();text=json.dumps(report,ensure_ascii=False,indent=2)
 if a.report:pathlib.Path(a.report).write_text(text+'\n')
 print(text);return 1 if report['errors'] else 0
if __name__=='__main__':sys.exit(main())
