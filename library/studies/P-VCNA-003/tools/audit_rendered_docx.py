import json,re,collections,zipfile,xml.etree.ElementTree as ET
from pathlib import Path
import pdfplumber
from PIL import Image,ImageChops
r=Path(__file__).resolve().parents[1];m=json.loads((r/'source_registry/Shell_Manifest.json').read_text());rows=[];a=[];out=r/'qa/inspection_crops';out.mkdir(exist_ok=True)
W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
clean=lambda s:''.join(c for c in s if not c.isspace() and c not in '\u200b\ufeff\u00ad')
for sh in m['shells']:
 tid=sh['template_id'];f=r/'TFL_Template_Library'/sh['planned_file_path'];pdf=r/'qa/docx_renders'/tid/(tid+'.pdf')
 with zipfile.ZipFile(f) as z:xml=ET.fromstring(z.read('word/document.xml'));tx=''.join(e.text or '' for e in xml.iter(W+'t'))
 wanted=collections.Counter(clean(tx));actual=collections.Counter();outside=[]
 with pdfplumber.open(pdf) as p:
  for j,pg in enumerate(p.pages,1):
   actual.update(clean(''.join(c['text'] for c in pg.chars)))
   bad=[c for c in pg.chars if c['text'].strip() and (c['x0']<35 or c['x1']>pg.width-25 or c['top']<30 or c['bottom']>pg.height-20)]
   if bad:outside.append(dict(page=j,text=''.join(c['text'] for c in bad)))
   png=r/'qa/docx_renders'/tid/f'page-{j}.png';idx=len(a)+1;a.append(dict(index=idx,template_id=tid,path=str(png),page=j))
   im=Image.open(png).convert('RGB');d=ImageChops.difference(im,Image.new('RGB',im.size,'white'));bb=d.point(lambda v:255 if v>35 else 0).getbbox()
   if bb:im.crop((max(0,bb[0]-12),max(0,bb[1]-12),min(im.width,bb[2]+12),min(im.height,bb[3]+12))).save(out/f'{idx:03}.png')
  rows.append(dict(template_id=tid,pages=len(p.pages),missing_rendered_characters=dict(wanted-actual),extra_rendered_characters=dict(actual-wanted),outside_page_safety_bounds=outside))
(r/'qa/DOCX_Visual_Page_Index.json').write_text(json.dumps(a,indent=2)+'\n');(r/'qa/DOCX_Render_Text_Audit.json').write_text(json.dumps(dict(method='Character multiset comparison: actual DOCX XML against rendered PDF, ignoring whitespace/zero-width/soft-hyphen chars. Detects missing/extra rendered glyphs, not correct order or clinical meaning.',records=rows),ensure_ascii=False,indent=2)+'\n')
print(json.dumps(dict(files=len(rows),pages=len(a),character_discrepancies=[x for x in rows if x['missing_rendered_characters'] or x['extra_rendered_characters']],outside_bounds=[x for x in rows if x['outside_page_safety_bounds']]),indent=2))
