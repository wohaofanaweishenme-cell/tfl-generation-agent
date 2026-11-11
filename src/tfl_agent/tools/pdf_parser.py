"""Preserve page/block IDs to anchor audit-grade evidence (PDF pages are 1-indexed)."""
import re
from pathlib import Path

def parse_sap(path):
    import fitz
    path=Path(path)
    if not path.exists(): raise FileNotFoundError(path)
    blocks=[]; section=None
    with fitz.open(str(path)) as pdf:
        for i, page in enumerate(pdf):
            for j, block in enumerate(sorted(page.get_text('blocks'),key=lambda b:(round(b[1],1),b[0]))):
                if len(block)<5 or not isinstance(block[4],str): continue
                text=' '.join(block[4].split())
                if not text: continue
                # Simple heading detection; retain original text even when heading detection fails.
                match=re.match(r'^(\d+(?:\.\d+){0,4})\s+([A-Z][^.;:]{3,90})$',text)
                if match: section=match.group(1)
                blocks.append({'block_id':f'sap:p{i+1}:b{j}', 'page':i+1, 'section':section,
                               'text':text,'bbox':[round(float(v),2) for v in block[:4]]})
    if not blocks: raise ValueError('No selectable text found in the PDF. This MVP does not perform OCR; supply a text-based SAP.')
    return {'filename':path.name,'blocks':blocks,'pages':max(b['page'] for b in blocks)}
