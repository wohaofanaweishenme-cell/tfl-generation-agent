"""Read v2.x source-template metadata without mutating original library files."""
from pathlib import Path
from tfl_agent.tools.io_utils import read_json

def load_library(root):
    root=Path(root).resolve()
    metadata=root/'metadata'/'Template_Metadata.json'
    if not metadata.exists():raise FileNotFoundError(f'Expected {metadata}. Use --library with an actual approved library.')
    payload=read_json(metadata)
    templates=payload['templates'] if isinstance(payload,dict) else payload
    result=[]; seen=set()
    for t in templates:
        ident=t.get('identity',t)
        tid=ident.get('template_id')
        if not tid:raise ValueError('Metadata template lacks template_id')
        if tid in seen:raise ValueError('Duplicate template ID: '+tid)
        seen.add(tid)
        rel=ident.get('file_path') or t.get('file_path')
        if not rel:raise ValueError('Template lacks file_path: '+tid)
        # metadata v2 examples use table/foo.docx, while final library has templates/table/foo.docx.
        candidates=[root/rel,root/'templates'/rel]
        # resolved path must be inside library and must exist
        valid=[]
        for candidate in candidates:
            candidate=candidate.resolve()
            if candidate.is_relative_to(root):valid.append(candidate)
        if not valid:raise ValueError('Unsafe metadata path outside library: '+rel)
        path=next((c for c in valid if c.is_file()),None)
        if path is None:raise FileNotFoundError('DOCX not found for template '+tid+': '+rel)
        if path.suffix.lower()!='.docx':raise ValueError('Only DOCX templates can be used: '+rel)
        result.append({**t,'identity':ident,'resolved_path':str(path)})
    kw_path=root/'index'/'Keyword_Index.json'
    keyword_index=read_json(kw_path) if kw_path.exists() else {}
    return {'templates':result,'index':keyword_index,'root':str(root)}
