"""Source-specific, image-reviewed page geometry plan. No content-list expansion.
All text comes from source word coordinates; page plans select physical regions.
No target adaptation, synthetic rows/statistics, or chart generation.
"""
import json,re,collections,hashlib,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];DID='SAP_001_11'
PAGES=json.loads((ROOT/'checkpoints/PDFKit_Word_Regions.json').read_text())
MAN=json.loads((ROOT/'source_registry/Shell_Manifest.json').read_text())
LINE=json.loads((ROOT/'checkpoints/PDFKit_Line_Regions.json').read_text())
GEO=json.loads((ROOT/'checkpoints/PDF_Character_and_Line_Geometry.json').read_text())
OUT=ROOT/'intermediate/Structured_Shells';OUT.mkdir(parents=True,exist_ok=True)
# page -> x positions of original columns, header start, body start/end.
# Baseline coordinates are top-left PDF points, verified against page previews.
PLAN={
11:([166,456],110,139,340),12:([96,180,341,420,592],98,153,455),13:([96,180,341,420,592],None,64,287),
14:([96,329,564],98,142,270),15:([96,174,308,449,604,713],98,153,280),
16:([96,259,329,380,493,600,698],98,153,235),17:([96,249,305,353,481,621,719],98,153,246),
18:([96,270,335,468,614,717],98,153,281),19:([96,224,378,568],98,142,192),
20:([96,284,378,568],109,153,406),21:([96,284,378,568],120,164,417),
22:([60,236,516,664],98,182,458),23:([115,398,586],142,209,310),24:([127,314,445,602],98,165,343),25:([127,314,445,602],98,165,343),
26:([96,137,235,290,359,411,461,509,599,689],98,148,365),
28:([96,137,227,374,463,562,653],98,148,322),29:([96,181,240,351,436,521,606,691],98,131,233),
30:([96,284,378,568],109,153,405),31:([96,241,379,569],120,164,428),32:([96,241,379,569],120,164,428),
33:([96,241,379,569],109,153,417),34:([96,241,379,569],98,142,292),
35:([96,358,578],98,142,269),36:([96,220,331,413,553],98,153,485),37:([96,220,331,413,553],None,64,252),
38:([96,447,610],98,165,300),39:([96,233,336,514,691],109,153,428),40:([96,240,312,458,617],87,142,417),
43:([96,233,337,477,630],109,131,244),44:([96,137,205,251,305,471,550,605,715],109,153,255),
45:([96,167,273,376,468,562,669],109,142,244),46:([96,165,238,311,402,475,566,638,711],120,164,244),
47:([96,183,274,366,480,572,685],109,153,233),48:([96,165,238,311,402,475,566,638,711],109,164,244),
49:([96,165,237,327,399,488,561,633,705],109,164,244),50:([96,165,238,311,402,475,566,638,711],109,164,266),
51:([96,165,238,311,402,493,565,638,704],109,164,244),52:([96,197,302,408,540,645],109,142,222),
53:([164,257,330,435,556],109,142,222),54:([96,189,287,377,483,660],109,131,233),
55:([96,146,186,225,267,361,497,542,588,633,712],129,179,369),
56:([96,195,410,532,653],109,153,255),57:([96,152,218,316,435,520,621,686],109,171,295),
58:([96,137,200,293,364,436,490,558,637,699],109,153,277),59:([218,350,488],109,131,233),
60:([96,209,326,435,563],120,142,288),61:([96,165,222,285,395,477,595,668],109,153,277),
62:([96,155,213,330,409,489,552,644,706],109,153,233),63:([96,161,214,308,368,428,504,572,650],109,143,245),
64:([248,331,414,544],109,131,233),65:([141,210,385,460,524,604],109,153,266),
66:([141,210,386,460,524],109,131,310),67:([252,339,464],109,131,222),
68:([96,137,235,290,359,411,461,509,599,689],129,179,397),69:([96,137,227,374,463,562,653],164,214,388),
70:([96,151,210,299,418,465,524,580,627,679],109,155,323),71:([168,224,282,371,491,537,611],110,150,318),
72:([218,273,332,421,541,587],110,150,234),73:([218,274,332,421,541],110,150,267),
74:([96,139,178,242,306,357,422,483,548,624,701],109,153,288),75:([96,158,209,290,391,531,661],109,142,321),
76:([96,146,183,251,319,383,454,515,577,639],109,142,288),
77:([96,158,329,403,449,490,567,619],109,153,299),78:([96,158,333,407,472,530,607,682],109,153,299),
79:([218,273,332,421,541,587],99,139,223),80:([197,265,341,452,590],109,142,277),
81:([96,170,254,420,541,693],109,137,239),82:([96,166,233,303],109,137,403),
83:([170,238,314,493,631],109,142,245),84:([96,144,276,333,368,400,460,499,619],109,153,299),
85:([96,153,209,266,323,379,436,493,549,606,663,719],128,183,263)}
# Logical source rows are geometrically grouped only across visible multiline cells.
# All other body row starts are obtained from actual y-baseline positions.
LIST_STARTS={26:[149.5,254.4,342.3,353.3],28:[149.5,232.3,298.3,309.3],29:[132.5,165.5,198.4,209.4,220.3],
43:[132.5,154.4,176.4,198.4,220.3,231.4],44:[154.4,176.4,198.4,220.3,242.4],45:[143.5,165.5,187.5,209.4,231.4],
46:[165.5,198.4,231.4],47:[154.4,187.5,220.3],48:[165.5,198.4,231.4],49:[165.5,198.4,231.4],
50:[165.5,209.4,253.3],51:[165.5,198.4,231.4],52:[143.5,176.4,209.4],53:[143.5,176.4,209.4],
54:[132.5,154.4,176.4,198.4,220.3],55:[180.4,268.2,356.1],56:[154.4,198.4,242.4],57:[172.4,227.4,282.4],
58:[154.4,209.4,264.4],59:[132.5,176.4,220.3],60:[143.5,176.4,209.4,242.4,275.3],61:[154.4,231.4,264.4],
62:[154.4,187.5,220.3],63:[144.0,187.9,231.9],64:[132.5,143.5,154.4,165.5,187.5,198.4,209.4,220.3],
65:[154.4,187.5,220.3,253.3],66:[132.5,187.5,242.4,297.3],67:[132.5,176.4,209.4],
68:[180.4,285.3,373.1,384.2],69:[215.2,298.1,364,375],70:[156,211.9,268,309.9],71:[151,206.9,262.8,304.8],
72:[151,178.9,206.9,220.9],73:[150.8,189.9,228.9,253.8],74:[154.4,198.4,242.4,275.4],
75:[143.5,198.4,253.3,308.3],76:[143.5,187.5,231.4,275.3],77:[154.4,198.4,242.4,286.3],78:[154.4,198.4,242.4,286.3],
79:[139.9,167.9,196,209.9],80:[143.5,187.5,231.4,264.4],81:[137.8,170.8,203.8,225.7],
82:[137.8,225.7,313.6,390.5],83:[143.5,176.4,209.4,231.4],84:[154.4,198.4,242.4,286.3],85:[184.2,195.3,206.2,217.2,228.1,250.1]}
# Physical footnotes, separately from programming notes; ranges may span wrapped lines.
FN={11:[(349,361)],13:[(294,306),(306,317),(317,329)],14:[(280,292),(292,304)],
15:[(288,300),(300,312)],16:[(244,256),(256,267),(267,278),(278,290)],17:[(255,267),(267,278),(278,289),(289,301)],
18:[(290,302),(302,313),(313,325)],22:[(468,480),(480,491),(491,503)],23:[(320,331),(331,342),(342,354)],24:[(353,364),(364,375),(375,387)],25:[(353,364),(364,375),(375,387)],
26:[(375,387),(387,398),(398,409),(408,421)],28:[(331,344)],29:[(242,255)],31:[(438,451)],32:[(438,451)],33:[(427,440)],34:[(302,315)],
35:[(280,292),(291,304)],37:[(262,274),(273,285),(284,296),(295,308)],38:[(309,321),(320,343),(342,354),(353,366)],40:[(427,440)],
41:[(349,367)],42:[(262,285)],44:[(264,277)],45:[(253,277)],46:[(253,266)],48:[(253,266)],56:[(264,277)],63:[(254,267)],
68:[(406,418),(417,429),(428,440),(439,452)],69:[(397,410)],70:[(338,351)],71:[(333,346)],74:[(309,323)],75:[(330,343)],76:[(297,310)],
77:[(308,321)],78:[(308,321)],84:[(308,321)]}
# Explicit group headers that span the visible children.
GROUP_HEADERS={26:[('Relationship to',7,3,98,109)],28:[('Action taken with',3,3,98,109)],
57:[('Alcohol History',1,2,109,122),('Smoking History',3,3,109,122),('Recreational Drug History',6,2,109,122)],
63:[('Normal Range',5,3,109,121)],68:[('Relationship to',7,3,129,141)],69:[('Action taken with',3,3,164,176)],
70:[('Normal Range',6,3,109,121)]}
# Source has no cell borders for rowspans: preserve visual blank continuation cells,
# do not assert merges just because label text is absent.
TABLE_MULTILINE={12:[(429.2,452)],15:[(154.4,197),(232.5,253.5)],19:[(143.5,164)],22:[(182.9,204)],36:[(313.4,334)],37:[(135.4,158)]}
# Snap note boundaries to actual physical baselines; avoid overlapping neighbouring notes.
for n,bands in list(FN.items()):
 ys=sorted(set(round(w['bbox'][1],3) for w in PAGES[n-1]['words']))
 anchors=[min(ys,key=lambda y:abs(y-a)) for a,b in bands]
 FN[n]=[(a-.4,anchors[i+1]-.4 if i+1<len(anchors) else max(a+1,bands[i][1])) for i,a in enumerate(anchors)]
ALL_ISSUES=[];EVIDENCE={};REVIEW=[]
def save(path,x):path.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def reg(n,b):
 p=PAGES[n-1];return dict(document_id=DID,pdf_page=n,bbox=[max(0,b[0]),max(0,b[1]),min(p['width_points'],b[2]),min(p['height_points'],b[3])],coordinate_system='pdf_points_top_left')
def select(n,b):return [w for w in PAGES[n-1]['words'] if b[0]-.1<=w['bbox'][0]<b[2]-.1 and b[1]<=w['bbox'][1]<b[3]]
def rows_for(ws):
 rows=[]
 for w in sorted(ws,key=lambda w:(w['bbox'][1],w['bbox'][0])):
  row=next((r for r in rows if abs(r[0]-w['bbox'][1])<2),None)
  if row is None:row=[w['bbox'][1],[]];rows.append(row)
  row[1].append(w)
 return sorted(rows,key=lambda r:r[0])
def text(ws):return '\n'.join(' '.join(w['text'] for w in sorted(r,key=lambda w:w['bbox'][0])) for _,r in rows_for(ws))
def bbox(ws,fallback=None):return [min(w['bbox'][0] for w in ws),min(w['bbox'][1] for w in ws),max(w['bbox'][2] for w in ws),max(w['bbox'][3] for w in ws)] if ws else fallback
def issue(st,cat,desc,regs=None,sev='warning'):
 i=dict(issue_id=f"{st['template_id']}_I{len(st['issues'])+1:03}",template_id=st['template_id'],severity=sev,category=cat,description=desc,status='open',source_regions=regs or st['source_regions']);st['issues'].append(i);ALL_ISSUES.append(i)
def evidence(n,b,why):
 k=f"{n}:"+','.join(f'{v:.3f}' for v in b)+':'+why
 rid='SRC_'+hashlib.sha256(k.encode()).hexdigest()[:16];EVIDENCE[rid]=dict(source_regions=[reg(n,b)],extraction_method='PDFKit word selection; image-reviewed geometry plan',note=why);return rid
PH=re.compile(r'^(?:[xX]+(?:[.,:T^][xX0-9]+)*|\(?[xX][^ ]*|<[^>]+>|\(N=[xX]+\)|ddMMMyyyy|HH:MM)$')
def element(st,kind,tx,n,b,pid,pointer=None,note=None):
 eid=f"E{len(st['source_elements'])+1:05}";oid=f"O{len(st['source_elements'])+1:05}";rid=evidence(n,b,kind)
 st['source_elements'].append(dict(element_id=eid,element_type=kind,metadata_pointer=pointer,occurrences=[dict(occurrence_id=oid,docx_locator=None,source_text=tx,role=kind,panel_id=pid,source_ref_ids=[rid],verification_status='unverified')],notes=note))
 return eid

def block(st,kind,tx,n,b,pid,eids=None,note=None):
 if eids is None:eids=[element(st,kind,tx,n,b,pid,note=note)]
 st['physical_blocks'].append(dict(block_id=f"B{len(st['physical_blocks'])+1:05}",kind=kind,display_order=len(st['physical_blocks']),panel_id=pid,source_regions=[reg(n,b)],source_docx_location=None,exact_text=tx,source_element_ids=eids,notes=note));return st['physical_blocks'][-1]

def addcell(st,n,pid,rid,cid,b,ws,rs=1,cs=1,header=False):
 tx=text(ws);cell=dict(cell_id=f"CELL{len(st['physical_cells'])+1:05}",panel_id=pid,row_id=rid,column_id=cid,row_span=rs,column_span=cs,text=tx,is_blank=not bool(ws),source_regions=[reg(n,b)])
 st['physical_cells'].append(cell)
 k='blank_cell' if not ws else 'header_cell' if header else 'placeholder_cell' if all(PH.match(w['text']) or w['text'] in ['(xx.x%)','xx','NA'] for w in ws) else 'body_cell'
 eid=element(st,k,tx,n,b,pid,note='Native source text/blank retained; geometry bounded by source columns and reviewed row bands.')
 block(st,'body' if header or k!='placeholder_cell' else 'placeholder',tx,n,b,pid,[eid],note=f"cell_id={cell['cell_id']}; row={rid}; column={cid}; spans={rs}x{cs}; {'header' if header else 'body'}")
 # Individual mixed-content placeholders retain separate occurrences at true coordinates.
 if ws and not header:
  for w in ws:
   if PH.match(w['text']):element(st,'placeholder',w['text'],n,w['bbox'],pid,note=f"Within {cell['cell_id']}; no target substitution requested.")
 return cell

def footnote(st,n,pid,lo,hi):
 ws=select(n,[0,lo,PAGES[n-1]['width_points'],hi]);tx=text(ws)
 if not ws:return
 b=bbox(ws);fid=f"FN{len(st['footnotes'])+1:03}";m=re.match(r'(\[[a-z]\]|\*\*|\*)[: ]',tx);marker=m[1] if m else None
 f=dict(footnote_id=fid,marker=marker,exact_text=tx,applies_to=[],category='placeholder' if re.search(r'<[Xx]+[.Xx]*>',tx) else 'study_specific',display_order=len(st['footnotes']),applies_to_refs=[dict(target_type='unknown',target_id=None,panel_id=pid,mapping_status='unresolved')],semantic_extraction_status='needs_review',semantic_rules=[],evidence_ref_ids=[evidence(n,b,'footnote')]);st['footnotes'].append(f)
 eid=element(st,'footnote',tx,n,b,pid,pointer=f"/footnotes/{len(st['footnotes'])-1}/exact_text",note='Physical note retained; semantic rules deferred. Region recorded by evidence_ref_ids and physical block.')
 block(st,'footnote',tx,n,b,pid,[eid],note=f'footnote_id={fid}')
 return f

def create_base(sh):return dict(schema_version='2.4',template_id=sh['template_id'],output_type=sh['output_type'],structural_family=sh['structural_family_candidate'],extraction_status='needs_review',source_regions=sh['source_regions'],source_docx_locations=[],physical_blocks=[],source_elements=[],occurrence_relations=[],footnotes=[],programming_notes=[],listing_rows=[],physical_cells=[],issues=[])

def rowmodel(st,spec,pid,label,header=False,placeholder=None):
 rid=f"{pid}_{'H' if header else 'R'}{sum(1 for r in spec.get('rows',st['listing_rows']) if r.get('id','').startswith(pid+('_H' if header else '_R')))+1:03}"
 if st['structural_family']=='listing':st['listing_rows'].append(dict(id=rid,order=len(st['listing_rows']),panel_id=pid,notes='Header row' if header else 'Physical source example row or ellipsis row; original blank continuation cells preserved. No patient/record values filled down.'))
 else:spec['rows'].append(dict(id=rid,order=len(spec['rows']),parent_id=None,label=label,role='other' if header else 'statistic' if re.fullmatch(r'n|Mean|STD|Median|Minimum|Maximum|n \(%\)',label) else 'category',statistic=None,placeholder=placeholder,editable=True))
 return rid

def make_grid(st,spec,n,pid,plan):
 starts,hs,bs,be=plan;ends=starts[1:]+[min(780,PAGES[n-1]['width_points']-40)]
 # x0 boundaries equal observed left padding minus 5; actual column rule endpoints are in GEO.
 bounds=[x-5 for x in starts]+[ends[-1]]
 cols=[]
 gh=GROUP_HEADERS.get(n,[])
 for j in range(len(starts)):
  b=[bounds[j],hs or bs,bounds[j+1],bs-3]
  ws=select(n,b) if hs else []
  ws=[w for w in ws if not any(lo<=w['bbox'][1]<hi and bounds[jj]<=((w['bbox'][0]+w['bbox'][2])/2)<bounds[jj+span] for _,jj,span,lo,hi in gh)]
  label=text(ws);cid=f'{pid}_C{j+1:02}';cols.append(cid)
  if st['structural_family']=='listing':spec['columns'].append(dict(id=cid,order=len(spec['columns']),label=label,source_variable=None,format=None,placeholder=None,editable=True))
  else:spec['columns'].append(dict(id=cid,order=len(spec['columns']),parent_id=None,label=label,role='arm' if re.search(r'Arm I',label) else 'statistic' if label in ['p-value','Odds Ratio (95% CI)','Hazard Ratio (95% CI)'] else 'stub' if j<2 else 'other',placeholder='(N=xx)' if '(N=xx)' in label else None,editable=True))
 # Separate explicit spanning group header row. Remaining native header is one multiline row.
 if hs:
  if gh:
   rid=rowmodel(st,spec,pid,'',True)
   used=set()
   for title,j,span,lo,hi in gh:
    b=[bounds[j],lo,bounds[j+span],hi];ws=select(n,[0,lo,PAGES[n-1]['width_points'],hi]);ws=[w for w in ws if bounds[j]<=((w['bbox'][0]+w['bbox'][2])/2)<bounds[j+span]]
    addcell(st,n,pid,rid,cols[j],b,ws,cs=span,header=True);used.update(range(j,j+span))
   for j in range(len(cols)):
    if j not in used:
     b=[bounds[j],hs,bounds[j+1],bs-3];addcell(st,n,pid,rid,cols[j],b,select(n,b),rs=2,header=True)
  rid=rowmodel(st,spec,pid,'',True)
  for j in range(len(cols)):
   if gh and j not in used:continue
   lo=max(t[4] for t in gh) if gh else hs
   b=[bounds[j],lo,bounds[j+1],bs-3];addcell(st,n,pid,rid,cols[j],b,select(n,b),header=True)
 bodywords=select(n,[bounds[0],bs,bounds[-1],be]);ys=[y for y,ws in rows_for(bodywords)]
 if n in LIST_STARTS:
  starts_y=[min(ys,key=lambda y:abs(y-a)) for a in LIST_STARTS[n]]
 else:
  starts_y=ys[:]
  for lo,hi in TABLE_MULTILINE.get(n,[]):
   starts_y=[y for y in starts_y if not (lo+1<y<hi)]
 rows=[]
 for i,y in enumerate(starts_y):
  top=y-1;bottom=starts_y[i+1]-1 if i+1<len(starts_y) else be
  # Row bands include native multiline material. Do not fill blank stubs or introduce new statistics.
  ws=select(n,[bounds[0],top,bounds[-1],bottom]);stubws=[w for w in ws if w['bbox'][0]<bounds[1]]
  if st['structural_family']=='table' and len(cols)>3:
   armidx=next((j for j,c in enumerate(spec['columns'][-len(cols):]) if re.search(r'Arm I\b',c['label'])),len(cols)-2)
   labelws=[w for w in ws if w['bbox'][0]<bounds[max(1,armidx)]]
   label=text(labelws)
  else:label=text(stubws)
  rid=rowmodel(st,spec,pid,label)
  rows.append(rid)
  for j,cid in enumerate(cols):
   b=[bounds[j],top,bounds[j+1],bottom];c=addcell(st,n,pid,rid,cid,b,select(n,b))
   if st['structural_family']=='table' and c['text'] and re.search(r'\b[xX]+\b|[xX]\.[xX]|<',c['text']):spec['cell_rules'].append(dict(row_id=rid,column_id=cid,display_format=None,placeholder=c['text'],rule_description='Source placeholder retained at its observed physical row/column; no analysis or target rule inferred.'))
 spec['panels'].append(dict(panel_id=pid,title=next((l['text'] for l in LINE[n-1]['lines'] if re.match(r'^(Table|Listing) [\d.]+ ',l['text'])),None),page_numbers=[n],column_ids=cols,row_ids=[r['id'] for r in (spec.get('rows',st['listing_rows'])) if r['id'].startswith(pid+'_')],notes='Source physical page/panel; continuation pages retain separate geometry within the same shell. Blank cells are visually empty within these row bands; no fill-down or invented rowspan.'))
 return [bounds[0],hs or bs,bounds[-1],be]

def other_content(st,n,pid,owned,grid,fnranges):
 # Build text blocks for all owned text outside grid and physical footnotes.
 lo,hi=owned[1],owned[3];ws=[w for w in PAGES[n-1]['words'] if lo<=w['bbox'][1]<hi]
 rem=[]
 for w in ws:
  x,y=w['bbox'][0],w['bbox'][1]
  if grid and grid[0]-.1<=x<grid[2]-.1 and grid[1]<=y<grid[3]:continue
  if any(a<=y<b for a,b in fnranges):continue
  rem.append(w)
 progs=[];other=[]
 for y,r in rows_for(rem):
  tx=text(r);b=bbox(r);kind='other';note=None
  if re.match(r'^(Table|Figure|Listing) [\d.]+ ',tx):kind='title'
  elif re.match(r'^Source:',tx):kind='source_line'
  elif re.match(r'^Form STAT|^Version Date:|^Page \d+ of ',tx):note='Corporate form footer retained separately; not a clinical footnote.'
  elif y<60:note='Corporate source header wrapper; retained for traceability, separate from shell title/header.'
  elif re.match(r'^P-VCNA-003|^ddMMMyyyy|^Page x/y|^Path\\Filename|^<Arm>|^<Parameter|^<Body system>|^<Scale>|^Ca 19.9',tx):kind='placeholder' if '<' in tx or 'ddMMM' in tx or 'x/y' in tx or 'Path' in tx else 'other'
  if re.match(r'Programming [Nn]ote|^If the relationship to study|^Below Detectable Value|^Please include \(1\)',tx) or progs and y<510 and not re.match(r'^(Form STAT|Version Date:|Page \d+ of |P-VCNA-003|Table |Listing |Figure )',tx):
   # Only adjacent source programming lines are grouped. Header/footer starts terminate a group.
   progs.append((y,r));continue
  if progs:
   emitprog(st,n,pid,progs);progs=[]
  block(st,kind,tx,n,b,pid,note=note)
  for w in r:
   if PH.match(w['text']):element(st,'placeholder',w['text'],n,w['bbox'],pid,note='Actual source placeholder; no replacement operation.')
 if progs:emitprog(st,n,pid,progs)

def emitprog(st,n,pid,rows):
 ws=[w for _,r in rows for w in r];tx=text(ws);b=bbox(ws)
 st['programming_notes'].append(dict(exact_text=tx,source_regions=[reg(n,b)],notes='Source note only; no shared-layout expansion, target adaptation, or simulation.'))
 block(st,'programming_note',tx,n,b,pid)

def make_figure(st,sh):
 n=sh['source_regions'][0]['pdf_page'];pid='P01';body=select(n,[90,98,PAGES[n-1]['width_points']-60,375 if n==41 else 307]);raw=text(body)
 ax=lambda v,l,u=None,r=None:dict(variable=v,label=l,unit=u,scale=None,range=r)
 if n==41:
  xp=ax('Time','Time Post-Dose (months)','months','As appropriate');yp=ax('Survival proportion','Proportion',None,'As appropriate');groups=['Arm'];legend=['Arm I (Nab-paclitaxel and gemcitabine) (N=xx) – linestyle = solid, colour = blue','Arm II (VCN-01 with Nab-paclitaxel and gemcitabine) (N=xx) – linestyle = solid, colour = green'];ftype='Procedure: PROC LIFETEST – survival plot';annotations=['Number of patients at risk over time to be presented below the x axis.']
 else:
  xp=ax('Visit','Visit',None,'As appropriate');yp=ax('Percentage','Percentage of patients',None,'0 - 100');groups=[];legend=[];ftype='Plot: Kaplan-Meier time to event plot';annotations=[]
 st['figure_spec']=dict(figure_type=ftype,panels=[dict(panel_id=pid,title=sh['original_title'],panel_description=raw,x_axis=xp,y_axis=yp)],groupings=groups,legend_items=legend,annotations=annotations,displayed_statistics=[],source_representation=dict(mode='description',description=raw,code_language=None,code_in_docx=False,image_in_docx=False,empty_plot_frame=False,notes='Source contains a bordered text specification box, not a plotting frame or plotted data. PROC name is not an executable program. No DOCX created at this stage.'),layout_notes=['Preserve actual native textual figure specification; do not create a plot, data, image or empty plotting frame.'])
 for y,r in rows_for(body):
  if any(a<=y<b for a,b in FN[n]):continue
  tx=text(r);kind='body';block(st,kind,tx,n,bbox(r),pid)
 for a,b in FN[n]:footnote(st,n,pid,a,b)
 other_content(st,n,pid,sh['source_regions'][0]['bbox'],[90,98,PAGES[n-1]['width_points']-60,375 if n==41 else 307],FN[n])
 # One description panel, no fabricated axis scale. Unknown units stay null.
 if n==41:issue(st,'source_reference_conflict','The programming note calls Figure 14.2.6 Duration of Response; Content List calls it Progression Free Survival. Preserve original inconsistent note; do not resolve clinically.')
 issue(st,'footnote_scope_pending','Physical footnote is captured verbatim with source bounds; typed applicability and semantic rules remain needs_review until supported interpretation. No global scope assumed.')

for sh in MAN['shells']:
 # Read persisted per-ID Source Record as input; assert original IDs/regions agree.
 sr=json.loads((ROOT/f"source_registry/Source_Records/{sh['template_id']}.json").read_text());assert sr['template_id']==sh['template_id'] and sr['source_regions']==sh['source_regions']
 st=create_base(sh)
 if st['structural_family']=='figure':make_figure(st,sh)
 else:
  if st['structural_family']=='table':
   spec=dict(rows=[],columns=[],statistics=[],denominator_rule=None,cell_rules=[],header_row_count=None,merged_cell_notes=['Only explicit multi-column header spans are asserted. Visually blank continuation cells are retained as blanks; row merging is not inferred from repeated or absent strings.'],orientation='landscape',layout_notes=['Columns and body row bands selected from source-region images and word coordinates; see checkpoints/Structure_Region_Plan.json and PDF character/line evidence.','Hierarchical labels remain physically distinct; parent_id linkage is reviewed separately. No common-statistic grid expansion.'],panels=[]);st['table_spec']=spec
  else:
   spec=dict(record_unit=None,columns=[],filters_or_inclusion_rules=[],group_by=['<Arm>'] if any('<Arm>' in c['text'] for c in sr['text_checkpoints'] if c['text']) else [],sort_by=[],identifiers_displayed=[],pagination_notes=[],layout_notes=['Native source columns and example rows retained, including literal option text and blank continuation cells.','No SDTM/ADaM variables, sorting direction, or record unit inferred.'],panels=[]);st['listing_spec']=spec
  for region_index,rr in enumerate(sh['source_regions']):
   n=rr['pdf_page'];pid=f'P{region_index+1:02}'
   if n not in PLAN:
    # Note-only continuation page; its panel association remains with preceding panel.
    pid=spec['panels'][-1]['panel_id'] if spec['panels'] else None
    other_content(st,n,pid,rr['bbox'],None,FN.get(n,[]));continue
   # Note-only leading region on a shared physical page is not another panel.
   if rr['bbox'][3]<PLAN[n][2]:
    pid=spec['panels'][-1]['panel_id'] if spec['panels'] else None;other_content(st,n,pid,rr['bbox'],None,[]);continue
   grid=make_grid(st,spec,n,pid,PLAN[n])
   for a,b in FN.get(n,[]):footnote(st,n,pid,a,b)
   other_content(st,n,pid,rr['bbox'],grid,FN.get(n,[]))
  if st['structural_family']=='table':
   spec['statistics']=list(dict.fromkeys(c['text'] for c in st['physical_cells'] if c['text'] in ['n','n (%)','n(%)','Mean','STD','Median','Minimum','Maximum']))
   spec['header_row_count']=max((2 if p['page_numbers'][0] in GROUP_HEADERS else 1 for p in spec['panels']),default=0)
  else:
   spec['identifiers_displayed']=list(dict.fromkeys(c['label'] for c in spec['columns'] if re.search(r'Patient\s+[Nn]umber',c['label'])))
   spec['pagination_notes']=[p['exact_text'] for p in st['programming_notes'] if 'include (1) and (2)' in p['exact_text']]
  # Footnotes [a,b,c] have source marker-supported scopes.
  if sh['original_tfl_number']=='14.3.10':
   for f in st['footnotes']:
    if f['marker']:
     marker=f['marker'];matched=[r['id'] for r in spec['rows'] if marker in r['label']]
     if matched:f['applies_to']=matched;f['applies_to_refs']=[dict(target_type='row',target_id=rid,panel_id=next(p['panel_id'] for p in spec['panels'] if rid in p['row_ids']),mapping_status='explicit') for rid in matched]
  if st['footnotes']:issue(st,'footnote_scope_pending','Each physical note has its own ID, text, display order, evidence region and source occurrence. Unmarked or unconfirmed scopes remain unknown/unresolved; semantic_rules=[] and needs_review. Marker-supported [a]/[b]/[c] associations are captured where visible.')
  # Page-specific ambiguity/source defects are not fixed by linear order.
  if sh['original_tfl_number']=='14.2.1.1':issue(st,'p_value_row_ownership','p-value placeholder between the Cox model and Log-rank label retained at its physical y-band with a blank label. Its statistical row ownership is unresolved; no association inferred from PDF text order.')
  if sh['original_tfl_number']=='14.3.1.1':issue(st,'unlabelled_source_rows','Three source placeholder rows have no visible row labels (between AE categories/sections). Preserve literal placeholder positions and blank labels; do not invent AE categories.')
  if sh['original_tfl_number']=='16.2.6.1':issue(st,'source_row_header_mismatch','The second source example row visibly contains Yes/No and date/time placeholders inconsistent with some displayed column headings. Preserve original content in its coordinate-supported columns; do not repair source.')
  if sh['original_tfl_number']=='16.2.9':issue(st,'true_blank_column','Respirations (breaths/min) column is physically blank in all displayed example rows. Do not insert xx placeholders or drop the column.')
  if sh['original_tfl_number']=='16.2.19':issue(st,'sparse_source_rows','Alternating physical example lines leave some diagnostic columns blank while others repeat. Rows preserved by actual baseline without filling down or asserting unseen rowspans.')
  if sh['original_tfl_number'] in ['14.3.2.1','16.2.7.1']:issue(st,'superscript_fidelity','Source renders Yes1 with superscript 1 and hierarchical adverse-event/SOC/PT text within a single physical column. Text and precise font/character bounds are retained; superscript styling must be preserved at DOCX build, not normalized away.')
  issue(st,'structure_review_pending','Image/coordinate extraction is persisted, but final cell-by-cell independent fidelity verification, implied row hierarchy/rowspan interpretation and superscript fidelity remain pending. extraction_status=needs_review; no DOCX or approval.')
 # Sort all physical blocks by source page/y/x, assign deterministic display order.
 st['physical_blocks'].sort(key=lambda b:(b['source_regions'][0]['pdf_page'],b['source_regions'][0]['bbox'][1],b['source_regions'][0]['bbox'][0]))
 for i,b in enumerate(st['physical_blocks']):b['display_order']=i
 save(OUT/f"{st['template_id']}.json",st)
 REVIEW.append(dict(template_id=st['template_id'],pages=sorted(set(r['pdf_page'] for r in sh['source_regions'])),image_inspection='performed_by_executing_agent',word_coordinate_inspection='performed',independent_review='not_run',extraction_status=st['extraction_status'],physical_cells=len(st['physical_cells']),footnotes=len(st['footnotes'])))
save(ROOT/'qa/Extraction_Issues.json',dict(schema_version='2.4',stage='structure',issues=ALL_ISSUES))
save(ROOT/'checkpoints/Source_Region_Evidence.json',dict(note='Region IDs used in Structured_Shell source_ref_ids/evidence_ref_ids. Not final metadata provenance.',evidence=EVIDENCE))
save(ROOT/'checkpoints/Structure_Region_Plan.json',dict(description='Agent-authored geometry plan based only on supplied source images and coordinates; not source clinical text.',page_column_body_plan=PLAN,listing_row_starts=LIST_STARTS,footnote_region_bands=FN,explicit_spanning_headers=GROUP_HEADERS,multiline_table_row_bands=TABLE_MULTILINE))
save(ROOT/'qa/Structure_Inspection_Checkpoint.json',dict(stage='structure',records=REVIEW,independent_review='not_run',docx_created=0))
p=json.loads((ROOT/'qa/Extraction_Progress.json').read_text());None if (ROOT/'qa/Extraction_Progress.identification_snapshot.json').exists() else save(ROOT/'qa/Extraction_Progress.identification_snapshot.json',p)
p.update(stage='structure',completed_ids=[],remaining_ids=p['manifest_ids'],blocked_ids=[],full_study_complete=False,notes=['64 schema-shaped structure extraction records persisted for all physical manifest shells. All retain needs_review, not counted completed merely because JSON exists.','All source shell images inspected with word coordinates; final independent/clinical QA not_run. Physical text and blank cells preserved; no target adaptation or DOCX.','Footnote semantics deferred with needs_review; applicability explicit only where markers support association.','See per-ID issues, geometry plan, word/character/line checkpoints and validation reports.'])
save(ROOT/'qa/Extraction_Progress.json',p)
print(json.dumps(dict(structures=len(REVIEW),cells=sum(r['physical_cells'] for r in REVIEW),footnotes=sum(r['footnotes'] for r in REVIEW),issues=len(ALL_ISSUES)),indent=2))
