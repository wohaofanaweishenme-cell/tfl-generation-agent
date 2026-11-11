"""Load both the original MVP library and the study-scoped v2.4 source library.

Source libraries are READ ONLY. This adapter does not rewrite their metadata,
bookmarks, source DOCX files, approval records, or statistical definitions.
"""
from pathlib import Path
from tfl_agent.tools.io_utils import read_json


def load_library(root):
    root = Path(root).resolve()
    mvp_metadata = root / 'metadata' / 'Template_Metadata.json'
    study_metadata = root / 'Study_Metadata.json'

    if mvp_metadata.is_file():
        metadata_path = mvp_metadata
        library_format = 'mvp'
        template_root = root / 'templates'
    elif study_metadata.is_file():
        metadata_path = study_metadata
        library_format = 'study_v2_4'
        template_root = root / 'TFL_Template_Library'
    else:
        raise FileNotFoundError(
            f'No supported library metadata in {root}. Expected '
            'metadata/Template_Metadata.json or Study_Metadata.json.'
        )

    payload = read_json(metadata_path)
    templates = payload.get('templates') if isinstance(payload, dict) else payload
    if not isinstance(templates, list):
        raise ValueError('Library metadata must contain a list of templates')

    result, seen = [], set()
    for t in templates:
        if not isinstance(t, dict):
            raise ValueError('Each template metadata record must be an object')
        ident = t.get('identity', t)
        tid = ident.get('template_id')
        if not isinstance(tid, str) or not tid:
            raise ValueError('Metadata template lacks template_id')
        if tid in seen:
            raise ValueError(f'Duplicate template ID: {tid}')
        seen.add(tid)

        rel = ident.get('file_path') or t.get('file_path')
        if not isinstance(rel, str) or not rel:
            raise ValueError(f'Template lacks file_path: {tid}')

        # Both layouts use a path relative to their own DOCX root.
        candidates = [(template_root / rel).resolve(), (root / rel).resolve()]
        safe = [p for p in candidates if p.is_relative_to(root)]
        if not safe:
            raise ValueError(f'Unsafe metadata path outside library: {rel}')
        path = next((p for p in safe if p.is_file()), None)
        if path is None:
            raise FileNotFoundError(f'DOCX not found for template {tid}: {rel}')
        if path.suffix.lower() != '.docx':
            raise ValueError(f'Only DOCX templates can be used: {rel}')

        locator = root / 'intermediate' / 'DOCX_Locator_Map' / f'{tid}.json'
        result.append({
            **t,
            'identity': ident,
            'resolved_path': str(path),
            'locator_map_path': str(locator.resolve()) if locator.is_file() else None,
        })

    keyword_path = root / 'index' / 'Keyword_Index.json'
    index = read_json(keyword_path) if keyword_path.is_file() else {}
    return {
        'templates': result,
        'index': index,
        'root': str(root),
        'metadata_path': str(metadata_path),
        'format': library_format,
        'library_id': payload.get('library_id') if isinstance(payload, dict) else None,
        'index_mode': 'global_keyword_index' if keyword_path.is_file() else 'per_template_keywords',
    }
