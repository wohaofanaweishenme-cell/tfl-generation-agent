"""Only sanctioned placeholders are modified; full source layout is preserved."""
import re
from pathlib import Path
from docx import Document

TOKEN_RE=re.compile(r'\{\{[A-Z][A-Z0-9_]*\}\}')

def iter_paragraphs(doc):
    for paragraph in doc.paragraphs:yield paragraph
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:yield paragraph

def _replace_in_para(p,replacements):
    original=p.text
    if not TOKEN_RE.search(original):return 0
    # Most placeholders are confined to one run; preserve its formatting.
    total=0
    for run in p.runs:
        for token,value in replacements.items():
            if token in run.text:
                total+=run.text.count(token)
                run.text=run.text.replace(token,value)
    # Handles a placeholder split over multiple runs, but may consolidate character styles
    # inside that paragraph. This is disclosed by the modification plan.
    residual=p.text
    if TOKEN_RE.search(residual):
        matches=[t for t in replacements if t in residual]
        if matches:
            for t in matches:
                total+=residual.count(t);residual=residual.replace(t,replacements[t])
            if p.runs:
                p.runs[0].text=residual
                for run in p.runs[1:]:run.text=''
    return total

def make_replacements(spec):
    requirements=spec['table_requirements']; stats=spec['statistical_requirements']
    replacements={'{{TITLE}}':spec['identity']['title'], '{{TFL_ID}}':spec['identity']['tfl_id']}
    for i,v in enumerate(requirements['column_requirements'],start=1):replacements[f'{{{{GROUP_{i}}}}}']=v
    for i,v in enumerate(requirements['row_requirements'],start=1):replacements[f'{{{{STAT_{i}}}}}']=v
    for i,v in enumerate(requirements['footnote_requirements'],start=1):replacements[f'{{{{FOOTNOTE_{i}}}}}']=v
    return replacements

def plan_modifications(template_path,spec):
    doc=Document(template_path)
    source_text='\n'.join(p.text for p in iter_paragraphs(doc))
    placeholders=set(TOKEN_RE.findall(source_text))
    replacements=make_replacements(spec)
    required=set(replacements)
    missing=sorted(required-placeholders)
    unexpected=sorted(placeholders-required)
    return {'template_path':str(template_path),'replacements':replacements,
            'missing_placeholders':missing,'unexpected_placeholders':unexpected,
            'safe_to_generate':not missing and not unexpected and bool(placeholders),
            'warning':'A split-run placeholder can consolidate runs in its paragraph; review DOCX formatting.'}

def generate_shell(template_path,spec,out_path):
    plan=plan_modifications(template_path,spec)
    if not plan['safe_to_generate']:
        return None,plan
    doc=Document(template_path)
    replacement_counts={k:0 for k in plan['replacements']}
    for p in iter_paragraphs(doc):
        for tok in replacement_counts:
            replacement_counts[tok]+=p.text.count(tok)
        _replace_in_para(p,plan['replacements'])
    unresolved=[p.text for p in iter_paragraphs(doc) if TOKEN_RE.search(p.text)]
    if unresolved:raise RuntimeError('Unresolved placeholders still present: '+str(unresolved[:3]))
    out_path=Path(out_path);out_path.parent.mkdir(parents=True,exist_ok=True)
    doc.save(out_path)
    plan['replacement_counts']=replacement_counts
    return str(out_path),plan
