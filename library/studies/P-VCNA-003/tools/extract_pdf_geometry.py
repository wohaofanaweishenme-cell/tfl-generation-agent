import json,pdfplumber
from pathlib import Path
root=Path(__file__).resolve().parents[1]
with pdfplumber.open(root/'original/SAP_001_11 copy 2.pdf') as d:
 pages=[]
 for n,p in enumerate(d.pages,1):
  chars=[{k:c.get(k) for k in ['text','x0','x1','top','bottom','fontname','size','upright']} for c in p.chars]
  edges=[{k:e.get(k) for k in ['x0','x1','top','bottom','orientation','linewidth','stroking_color']} for e in p.edges]
  pages.append(dict(pdf_page=n,width_points=p.width,height_points=p.height,chars=chars,edges=edges))
(root/'checkpoints/PDF_Character_and_Line_Geometry.json').write_text(json.dumps(pages,ensure_ascii=False,indent=2))
print('86-page character/font/edge checkpoint saved')
