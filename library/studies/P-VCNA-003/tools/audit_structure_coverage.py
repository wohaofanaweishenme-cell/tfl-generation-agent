import json,collections
from pathlib import Path
r=Path(__file__).resolve().parents[1]
pages=json.loads((r/'checkpoints/PDFKit_Word_Regions.json').read_text());man=json.loads((r/'source_registry/Shell_Manifest.json').read_text());results=[]
for sh in man['shells']:
 st=json.loads((r/f"intermediate/Structured_Shells/{sh['template_id']}.json").read_text())
 for reg in sh['source_regions']:
  n=reg['pdf_page'];a,b,c,d=reg['bbox'];wanted=collections.Counter(w['text'] for w in pages[n-1]['words'] if a<=w['bbox'][0]<c and b<=w['bbox'][1]<d)
  actual=collections.Counter(t for bl in st['physical_blocks'] if bl['source_regions'][0]['pdf_page']==n for t in (bl['exact_text'] or '').split())
  missing=wanted-actual;extra=actual-wanted
  if missing or extra:results.append(dict(template_id=sh['template_id'],pdf_page=n,missing=dict(missing),extra=dict(extra)))
(r/'qa/Structure_Text_Coverage.json').write_text(json.dumps(dict(method='Compare source PDFKit token counts per owned page region against physical_blocks only (not nested source_elements). Whitespace normalized; no semantic, merge or typography certification.',mismatches=results),ensure_ascii=False,indent=2))
print(json.dumps(results,ensure_ascii=False,indent=2))
