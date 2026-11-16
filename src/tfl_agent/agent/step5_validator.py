import re
from pathlib import Path
from docx import Document
from jsonschema import Draft202012Validator
from tfl_agent.tools.io_utils import read_json
from tfl_agent.tools.docx_editor import iter_paragraphs


def validate_spec_document(payload,schema_path,sap):
    schema=read_json(schema_path)
    errors=[str(e) for e in Draft202012Validator(schema).iter_errors(payload)]
    lookup={b['block_id']:b for b in sap['blocks']}
    for spec in payload.get('specifications',[]):
        provenance=spec.get('provenance',{})
        evidence={e.get('ref_id'):e for e in provenance.get('evidence',[])}
        for eid,e in evidence.items():
            if eid not in lookup:errors.append('Evidence ID not found in SAP: '+str(eid));continue
            b=lookup[eid]
            if e.get('document_kind')!='sap_body' or e.get('exact_text')!=b['text'] or e.get('page_numbers')!=[b['page']]:
                errors.append('Evidence text/page mismatch: '+eid)
        for link in provenance.get('field_links',[]):
            for eid in link.get('ref_ids',[]):
                if eid not in evidence:errors.append('Dangling evidence ref: '+eid)
    return {'schema_valid':not errors,'errors':errors}

def validate_shell(path,spec,plan):
    path=Path(path)
    if not path.exists():return {'valid':False,'checks':{},'issues':['Output DOCX missing']}
    doc=Document(path)
    texts=[p.text for p in iter_paragraphs(doc)]
    all_text='\n'.join(texts)
    checks={
        'tfl_title':spec['identity']['title'] in all_text,
        'statistics':all(x in all_text for x in spec['table_requirements']['row_requirements']),
        'treatment_columns':all(x in all_text for x in spec['table_requirements']['column_requirements']),
        'footnotes':all(x in all_text for x in spec['table_requirements']['footnote_requirements']),
        'has_table':len(doc.tables)>0,
        'no_unresolved_placeholders':not bool(re.search(r'\{\{[A-Z][A-Z0-9_]*\}\}',all_text)),
        'all_replacements_applied':all(x>0 for x in plan.get('replacement_counts',{}).values())
    }
    if plan.get('editing_mode') == 'verified_bookmark_draft':
        from tfl_agent.tools.bookmark_adapter import _norm
        edits = plan.get('edits', [])
        checks['bookmark_edits_applied'] = (
            len(plan.get('applied_bookmarks', [])) == len(edits) and
            all((not e['new_text']) or _norm(e['new_text']) in _norm(all_text)
                for e in edits)
        )
        checks['source_sha_recorded'] = bool(plan.get('source_sha256'))
        # A structurally valid DOCX remains a draft pending manual clinical review.
        checks['review_required_not_suppressed'] = bool(plan.get('review_required'))
    return {'valid':all(checks.values()),'checks':checks,'issues':[k for k,v in checks.items() if not v]}
