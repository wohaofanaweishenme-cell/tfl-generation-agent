"""Native editable Word renderer for persisted source structures, v2.4.
Preserves source text and physical source page/panel ordering. No target adaptation.
"""
import json,re,copy,hashlib,zipfile,collections
from pathlib import Path
from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH,WD_BREAK,WD_LINE_SPACING,WD_TAB_ALIGNMENT
from docx.enum.table import WD_TABLE_ALIGNMENT,WD_CELL_VERTICAL_ALIGNMENT,WD_ROW_HEIGHT_RULE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
ROOT=Path(__file__).resolve().parents[1]
MAN=json.loads((ROOT/'source_registry/Shell_Manifest.json').read_text())
EV=json.loads((ROOT/'checkpoints/Source_Region_Evidence.json').read_text())['evidence']
WORDS=json.loads((ROOT/'checkpoints/PDFKit_Word_Regions.json').read_text())
GEO=json.loads((ROOT/'checkpoints/PDF_Character_and_Line_Geometry.json').read_text())
SOUT=ROOT/'intermediate/Structured_Shells';MAPOUT=ROOT/'intermediate/DOCX_Locator_Map';MAPOUT.mkdir(parents=True,exist_ok=True)
for typ in ['table','figure','listing']:(ROOT/'TFL_Template_Library'/typ).mkdir(parents=True,exist_ok=True)
QA=[];RECORDS=[]
W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def sub(el,name,**attrs):
 e=OxmlElement('w:'+name)
 for k,v in attrs.items():e.set(qn('w:'+k),str(v))
 el.append(e);return e

def fmtpara(p,left=0,before=0,after=0,line=10.99,align=None):
 f=p.paragraph_format;f.left_indent=Pt(max(0,left));f.right_indent=Pt(0);f.space_before=Pt(max(0,before));f.space_after=Pt(after);f.line_spacing=Pt(line);f.widow_control=False;f.keep_together=False
 if align is not None:p.alignment=align

def selected(n,b):return [w for w in WORDS[n-1]['words'] if b[0]-.1<=w['bbox'][0]<b[2]-.1 and b[1]-.1<=w['bbox'][1]<b[3]-.1]
def ordered(ws):
 rs=[]
 for w in sorted(ws,key=lambda w:(w['bbox'][1],w['bbox'][0])):
  row=next((r for r in rs if abs(r[0]-w['bbox'][1])<2),None)
  if row is None:row=[w['bbox'][1],[]];rs.append(row)
  row[1].append(w)
 return [w for _,rs in sorted(rs) for w in sorted(rs,key=lambda w:w['bbox'][0])]

def excluded(b):return bool(b.get('notes') and ('Corporate source header' in b['notes'] or 'Corporate form footer' in b['notes']))

class Renderer:
 def __init__(self,sh,st):
  self.sh=sh;self.st=st;self.tid=sh['template_id'];self.doc=Document();self.nextbid=0;self.elems={e['element_id']:e for e in st['source_elements']};self.rendered=set();self.exclusions=[];self.linked=set();self.issues=[]
  sec=self.doc.sections[0];sec.page_width=Pt(841.92);sec.page_height=Pt(595.32);sec.top_margin=Pt(48);sec.bottom_margin=Pt(36);sec.left_margin=Pt(54);sec.right_margin=Pt(54);sec.header_distance=Pt(12);sec.footer_distance=Pt(12)
  style=self.doc.styles['Normal'];style.font.name='Calibri';style.font.size=Pt(9);style.paragraph_format.space_after=Pt(0)
  self.doc.styles['Title'].font.name='Calibri';self.doc.styles['Title'].font.size=Pt(9);self.doc.styles['Title'].font.color.rgb=__import__('docx').shared.RGBColor(0,0,0)
  for sty in self.doc.styles:
   for border in list(sty.element.iter(qn('w:pBdr'))):border.getparent().remove(border)
  for e in st['source_elements']:
   for o in e['occurrences']:o['docx_locator']=None;o['verification_status']='unverified'
  self.start=self.tid+'_START';self.end=self.tid+'_END'
  self.doc.core_properties.title=sh['original_title'];self.doc.core_properties.subject='Source TFL shell '+str(sh['original_tfl_number']);self.doc.core_properties.author='';self.doc.core_properties.comments=''
 def mark(self,p,name,collapsed=False):
  bid=self.nextbid;self.nextbid+=1;a=OxmlElement('w:bookmarkStart');a.set(qn('w:id'),str(bid));a.set(qn('w:name'),name);z=OxmlElement('w:bookmarkEnd');z.set(qn('w:id'),str(bid))
  p._p.append(a)
  if collapsed:p._p.append(z)
  return a,z
 def rich(self,p,b):
  tx=b['exact_text'] or '';n=b['source_regions'][0]['pdf_page'];bb=b['source_regions'][0]['bbox'];sourcewords=ordered(selected(n,bb));tokens=list(re.finditer(r'\S+',tx));spans=[]
  for eid in b['source_element_ids']:
   el=self.elems[eid]
   for o in el['occurrences']:
    if o['occurrence_id'] in self.linked:continue
    ot=o['source_text']
    if ot==tx:lo,hi=0,len(tx)
    else:
     rb=EV[o['source_ref_ids'][0]]['source_regions'][0]['bbox'];wordidx=next((j for j,w in enumerate(sourcewords) if w['text']==ot and max(abs(w['bbox'][k]-rb[k]) for k in range(4))<.15),None)
     if wordidx is None or wordidx>=len(tokens):
      self.issues.append(('unlocated_occurrence',o['occurrence_id']+' could not be resolved in owned block '+b['block_id']));continue
     lo,hi=tokens[wordidx].span()
     if tx[lo:hi]!=ot:self.issues.append(('unlocated_occurrence',o['occurrence_id']+' token differs'));continue
    name='O_'+o['occurrence_id'];bid=self.nextbid;self.nextbid+=1
    spans.append((lo,hi,bid,name,o));self.linked.add(o['occurrence_id']);o['docx_locator']='bookmark:'+name
  # Transfer per-character source typography, including 6/6.5-point superscripts.
  styles={}
  if len(sourcewords)==len(tokens):
   for w,tok in zip(sourcewords,tokens):
    chars=[c for c in GEO[n-1]['chars'] if c['text'].strip() and w['bbox'][0]-.4<=c['x0']<w['bbox'][2]+.1 and w['bbox'][1]-1<=c['top']<w['bbox'][3]+.5]
    chars.sort(key=lambda c:c['x0']);word=''.join(c['text'] for c in chars)
    if word==w['text']:
     for j,c in enumerate(chars):styles[tok.start()+j]=dict(italic='Italic' in c['fontname'],bold='Bold' in c['fontname'],sup=float(c['size'])<7.5)
  opens=collections.defaultdict(list);closes=collections.defaultdict(list)
  for lo,hi,bid,name,o in spans:opens[lo].append((hi,bid,name));closes[hi].append((lo,bid,name))
  # Boundary order: close nested ranges first; open whole block before token ranges.
  disp=tx
  if re.match(r'^P-VCNA-003 ddMMMyyyy',tx):disp=tx.replace(' ','\t',1);p.paragraph_format.tab_stops.add_tab_stop(Pt(681),WD_TAB_ALIGNMENT.RIGHT)
  elif 'Path\\Filename Page x/y' in tx:disp=tx.replace('Path\\Filename ','Path\\Filename\t',1);p.paragraph_format.tab_stops.add_tab_stop(Pt(681),WD_TAB_ALIGNMENT.RIGHT)
  positions=sorted(set([0,len(tx),*opens,*closes,*styles,*[i+1 for i in styles]]));active_style={}
  for i,pos in enumerate(positions):
   # Empty bookmarks need start before end at the same offset.
   for hi,bid,name in sorted(opens[pos],key=lambda z:(-z[0],z[1])):
    el=OxmlElement('w:bookmarkStart');el.set(qn('w:id'),str(bid));el.set(qn('w:name'),name);p._p.append(el)
   for lo,bid,name in sorted(closes[pos],key=lambda z:(-z[0],-z[1])):
    el=OxmlElement('w:bookmarkEnd');el.set(qn('w:id'),str(bid));p._p.append(el)
   if i+1<len(positions):
    txt=disp[pos:positions[i+1]]
    if txt:
     run=p.add_run(txt);run.font.name='Calibri';run.font.size=Pt(9);sty=styles.get(pos,{})
     run.italic=sty.get('italic',b['kind']=='programming_note');run.bold=sty.get('bold',False)
     if sty.get('sup'):run.font.superscript=True
  self.rendered.add(b['block_id'])
 def paragraph(self,b,cursor):
  bb=b['source_regions'][0]['bbox'];tx=b['exact_text'] or '';p=self.doc.add_paragraph();ishead=b['kind']=='title'
  if ishead:p.style='Title'
  right=tx=='Page x/y';left=0 if ishead or right else max(0,bb[0]-54)
  fmtpara(p,left=left,before=max(0,bb[1]-cursor),line=10.99,align=WD_ALIGN_PARAGRAPH.CENTER if ishead else WD_ALIGN_PARAGRAPH.RIGHT if right else WD_ALIGN_PARAGRAPH.LEFT)
  self.rich(p,b)
  return max(cursor,bb[1])+max(10.99,len(tx.split('\n'))*10.99)
 def grid(self,blocks,panel,cursor):
  cells=[c for c in self.st['physical_cells'] if c['panel_id']==panel];byrow=collections.OrderedDict()
  for c in cells:byrow.setdefault(c['row_id'],[]).append(c)
  rows=list(byrow);spec=self.st[self.st['structural_family']+'_spec'];pan=next(p for p in spec['panels'] if p['panel_id']==panel);cols=pan['column_ids'];n=cells[0]['source_regions'][0]['pdf_page'];x0=min(c['source_regions'][0]['bbox'][0] for c in cells);top=min(c['source_regions'][0]['bbox'][1] for c in cells);bottom=max(c['source_regions'][0]['bbox'][3] for c in cells)
  # Gap before native table; invisible paragraph contains no source/QA text.
  gap=self.doc.add_paragraph();fmtpara(gap,before=0,after=max(0,top-cursor),line=.1);gap.paragraph_format.space_after=Pt(max(0,top-cursor-.1))
  widths=[]
  for cid in cols:
   single=next(c for c in cells if c['column_id']==cid and c['column_span']==1)
   b=single['source_regions'][0]['bbox'];widths.append(b[2]-b[0])
  table=self.doc.add_table(rows=len(rows),cols=len(cols));table.autofit=False;table.alignment=WD_TABLE_ALIGNMENT.LEFT
  pr=table._tbl.tblPr;sub(pr,'tblInd',w=round((x0-54)*20),type='dxa');borders=sub(pr,'tblBorders')
  for side in ['top','left','bottom','right','insideH','insideV']:sub(borders,side,val='nil')
  mar=sub(pr,'tblCellMar')
  for side in ['top','bottom','left','right']:sub(mar,side,w=0,type='dxa')
  for j,width in enumerate(widths):table.columns[j].width=Pt(width)
  rawcells={(i,j):table.cell(i,j) for i in range(len(rows)) for j in range(len(cols))}
  for i,rid in enumerate(rows):
   row=table.rows[i];cs=byrow[rid];row.height=Pt(max(c['source_regions'][0]['bbox'][3]-c['source_regions'][0]['bbox'][1] for c in cs if c['row_span']==1) if any(c['row_span']==1 for c in cs) else 11);row.height_rule=WD_ROW_HEIGHT_RULE.AT_LEAST
   if '_H' in rid:sub(row._tr.get_or_add_trPr(),'tblHeader')
   sub(row._tr.get_or_add_trPr(),'cantSplit')
   for c in cs:
    j=cols.index(c['column_id']);cell=rawcells[i,j]
    if c['row_span']>1 or c['column_span']>1:cell=cell.merge(rawcells[i+c['row_span']-1,j+c['column_span']-1])
    cell.width=Pt(sum(widths[j:j+c['column_span']]));cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.TOP
    tcpr=cell._tc.get_or_add_tcPr();m=sub(tcpr,'tcMar')
    for side in ['top','bottom','left','right']:sub(m,side,w=0,type='dxa')
    # Source table uses horizontal rules, no invented full grid/shading.
    cb=sub(tcpr,'tcBorders')
    if i==0:sub(cb,'top',val='single',sz=4,color='606060')
    if '_H' in rid and (i+1==len(rows) or '_H' not in rows[i+1]):sub(cb,'bottom',val='single',sz=4,color='606060')
    if i+c['row_span']==len(rows):sub(cb,'bottom',val='single',sz=4,color='606060')
    p=cell.paragraphs[0];bb=c['source_regions'][0]['bbox'];sw=selected(n,bb);delta=max(0,min((w['bbox'][1] for w in sw),default=bb[1])-bb[1]);fmtpara(p,left=max(0,min((w['bbox'][0] for w in sw),default=bb[0])-bb[0]),before=delta,line=10.99)
    b=next(b for b in blocks if 'cell_id='+c['cell_id']+';' in (b.get('notes') or ''))
    self.rich(p,b)
  return bottom
 def figurebox(self,blocks,cursor):
  top=min(b['source_regions'][0]['bbox'][1] for b in blocks);left=min(b['source_regions'][0]['bbox'][0] for b in blocks)
  gap=self.doc.add_paragraph();fmtpara(gap,line=.1,after=max(0,top-cursor-.1))
  table=self.doc.add_table(rows=1,cols=1);table.autofit=False;table.columns[0].width=Pt(681);sub(table._tbl.tblPr,'tblInd',w=round((90.5-54)*20),type='dxa')
  borders=sub(table._tbl.tblPr,'tblBorders')
  for side in ['top','left','bottom','right']:sub(borders,side,val='single',sz=4,color='606060')
  cell=table.cell(0,0);cell.width=Pt(681);cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.TOP
  mar=sub(cell._tc.get_or_add_tcPr(),'tcMar')
  for side in ['top','bottom']:sub(mar,side,w=20,type='dxa')
  for side in ['left','right']:sub(mar,side,w=100,type='dxa')
  current=top
  for i,b in enumerate(blocks):
   p=cell.paragraphs[0] if i==0 else cell.add_paragraph();bb=b['source_regions'][0]['bbox'];fmtpara(p,before=max(0,bb[1]-current),line=10.99);self.rich(p,b);current=max(current,bb[1])+max(10.99,len((b['exact_text'] or '').split('\n'))*10.99)
  return current+2
 def build(self):
  # Real collapsed shell START before all substantive source content.
  p=self.doc.add_paragraph();fmtpara(p,line=.1);self.mark(p,self.start,True)
  groups=collections.OrderedDict()
  for b in self.st['physical_blocks']:
   if excluded(b):
    self.exclusions.extend(b['source_element_ids']);continue
   groups.setdefault(b['source_regions'][0]['pdf_page'],[]).append(b)
  for pageidx,(n,blocks) in enumerate(groups.items()):
   if pageidx:
    p=self.doc.add_paragraph();fmtpara(p,line=.1);p.add_run().add_break(WD_BREAK.PAGE)
   cursor=48
   handled=set()
   for b in blocks:
    if b['block_id'] in self.rendered:continue
    if self.st['structural_family']=='figure' and b['kind'] in ['body','footnote']:
     fbs=[q for q in blocks if q['kind'] in ['body','footnote']];cursor=self.figurebox(fbs,cursor);continue
    if 'cell_id=' in (b.get('notes') or ''):
     pid=b['panel_id']
     if pid not in handled:
      bs=[q for q in blocks if q['panel_id']==pid and 'cell_id=' in (q.get('notes') or '')];cursor=self.grid(bs,pid,cursor);handled.add(pid)
    else:cursor=self.paragraph(b,cursor)
  p=self.doc.add_paragraph();fmtpara(p,line=.1);self.mark(p,self.end,True)
  path=ROOT/'TFL_Template_Library'/self.sh['planned_file_path'];self.doc.save(path)
  # Inspect actual document.xml bookmark text, order, containment and all note pointers.
  with zipfile.ZipFile(path) as z:xml=__import__('xml.etree.ElementTree',fromlist=['']).fromstring(z.read('word/document.xml'))
  seq=list(xml.iter());starts={};ends={}
  for i,x in enumerate(seq):
   if x.tag==W+'bookmarkStart':starts[x.attrib[W+'name']]=(i,x.attrib[W+'id'])
   elif x.tag==W+'bookmarkEnd':ends[x.attrib[W+'id']]=i
  sa,sid=starts[self.start];ea,eid=starts[self.end];assert sa<ends[sid]<ea<ends[eid]
  norm=lambda t:re.sub(r'\s+',' ',__import__('unicodedata').normalize('NFKC',t)).strip()
  verified=0
  for el in self.st['source_elements']:
   for o in el['occurrences']:
    if o['docx_locator']:
     a,bi=starts[o['docx_locator'][9:]];b=ends[bi];tx=''.join((x.text or '') if x.tag==W+'t' else '\n' if x.tag in [W+'br',W+'tab'] else '' for x in seq[a+1:b]);assert ends[sid]<a<b<ea,(self.tid,o['occurrence_id'],'scope');assert norm(tx)==norm(o['source_text']),(self.tid,o['occurrence_id'],repr(tx),repr(o['source_text']));o['verification_status']='verified';verified+=1
  boundary=dict(start_marker=self.start,end_marker=self.end,document_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),verification_status='verified',includes_footnotes=True,scope_policy='complete_source_shell_including_owned_notes',notes='Actual collapsed boundary order/containment and source occurrence text inspected in word/document.xml. All physical footnotes materialized as visible editable body paragraphs. Corporate header/logo/form footer excluded consistently; source study/date/path/Page x/y placeholders retained. Render fidelity is recorded separately, not inferred here.')
  for eid in self.exclusions:
   self.elems[eid]['notes']=(self.elems[eid].get('notes') or '')+' Excluded corporate wrapper/form footer by documented policy; retained in source inventory, not silently removed.'
  issues=[]
  if self.exclusions:issues.append(dict(issue_id=self.tid+'_DX001',template_id=self.tid,severity='info',category='documented_wrapper_exclusion',description=f'{len(self.exclusions)} corporate header/form-footer occurrences excluded by consistent policy; source records retained with null locator and unverified state. Substantive source study/date/path/page placeholders and notes remain inside the boundary.',status='deferred',source_regions=[]))
  for cat,desc in self.issues:issues.append(dict(issue_id=self.tid+f'_DX{len(issues)+1:03}',template_id=self.tid,severity='warning',category=cat,description=desc,status='open',source_regions=self.st['source_regions']))
  if self.st['extraction_status']=='needs_review':issues.append(dict(issue_id=self.tid+f'_DX{len(issues)+1:03}',template_id=self.tid,severity='warning',category='source_structure_pending',description='Source structure remains needs_review. Physical source content has been rendered without repairing source ambiguities; consult structure issues. DOCX construction does not grant clinical/source approval.',status='open',source_regions=self.st['source_regions']))
  mp=dict(schema_version='2.4',template_id=self.tid,file_path=self.sh['planned_file_path'],docx_boundary=boundary,source_elements=copy.deepcopy(self.st['source_elements']),occurrence_relations=self.st['occurrence_relations'],issues=issues)
  save(MAPOUT/(self.tid+'.json'),mp);save(SOUT/(self.tid+'.json'),self.st);QA.extend(issues)
  RECORDS.append(dict(template_id=self.tid,file_path=self.sh['planned_file_path'],sha256=boundary['document_sha256'],verified_occurrences=verified,unlocated_occurrences=sum(1 for e in self.st['source_elements'] for o in e['occurrences'] if not o['docx_locator']),source_pages=list(groups),native_tables=len(self.doc.tables),render_status='not_run',visual_inspection='not_run'))

if __name__=='__main__':
 import sys
 subset=set(sys.argv[1:])
 if subset and (ROOT/'qa/DOCX_Build_Checkpoint.json').exists():
  RECORDS.extend(x for x in json.loads((ROOT/'qa/DOCX_Build_Checkpoint.json').read_text())['records'] if x['template_id'] not in subset)
  QA.extend(x for x in json.loads((ROOT/'qa/DOCX_Generation_Issues.json').read_text())['issues'] if x['template_id'] not in subset)
 for sh in MAN['shells']:
  if subset and sh['template_id'] not in subset:continue
  st=json.loads((SOUT/(sh['template_id']+'.json')).read_text());Renderer(sh,st).build()
 save(ROOT/'qa/DOCX_Generation_Issues.json',dict(schema_version='2.4',stage='docx',issues=QA))
 save(ROOT/'qa/DOCX_Build_Checkpoint.json',dict(records=RECORDS,wrapper_policy='Exclude corporate logos/headers and pure Form STATt004/Version Date/printed PDF page footer. Retain all actual shell study/date/path/Page x/y placeholders and all substantive notes. No native Word endnote source exists (PDF inputs only).',bookmark_scope_check='actual XML checked',source_text_check='actual XML checked',render_check='not_run'))
 print('Built',len(RECORDS),'DOCX files;',sum(r['verified_occurrences'] for r in RECORDS),'verified occurrence scopes')
