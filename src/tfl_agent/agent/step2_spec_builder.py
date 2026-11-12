"""Evidence-backed target Table requirements; preserve provenance and uncertain scope.

A verified SAP quotation may explicitly enumerate several list values. The model
sometimes cites only the first item; the remaining *literal* items can reuse the
same evidence, but never by merely being in the same block or same field.
"""
import json
import re
import unicodedata
from pathlib import Path
from tfl_agent.tools.sap_search import SAPIndex, baseline_queries

STAT_KEYS_STR = ['analysis_topic', 'endpoint_name', 'endpoint_type']
STAT_KEYS_ARR = [
    'analysis_population', 'analysis_methods', 'treatment_groups',
    'treatment_comparisons', 'visits_or_timepoints', 'statistics_to_display',
    'variables_to_display', 'stratification_factors', 'notes',
]
TABLE_KEYS_ARR = ['row_requirements', 'column_requirements', 'footnote_requirements']

# The named clinical endpoint is essential for endpoint tables, but NOT for
# demographic/baseline, safety or disposition summaries.
BASE_ESSENTIAL = [
    '/statistical_requirements/analysis_population',
    '/statistical_requirements/analysis_methods',
    '/statistical_requirements/treatment_groups',
    '/statistical_requirements/statistics_to_display',
    '/table_requirements/row_requirements',
    '/table_requirements/column_requirements',
]
ENDPOINT_ESSENTIAL = '/statistical_requirements/endpoint_name'


def _get_pointer(obj, ptr):
    node = obj
    for piece in ptr.strip('/').split('/'):
        piece = piece.replace('~1', '/').replace('~0', '~')
        node = node[int(piece)] if isinstance(node, list) else node[piece]
    return node


def _set_pointer(obj, ptr, value):
    parts = ptr.strip('/').split('/')
    node = obj
    for p in parts[:-1]:
        node = node[int(p)] if isinstance(node, list) else node[p]
    p = parts[-1]
    if isinstance(node, list):
        node[int(p)] = value
    else:
        node[p] = value


def _present_fields(section, base):
    for key, val in section.items():
        if isinstance(val, list):
            for idx, item in enumerate(val):
                if isinstance(item, str) and item.strip():
                    yield f'{base}/{key}/{idx}'
        elif isinstance(val, str) and val.strip():
            yield f'{base}/{key}'


def _issue(path, kind, desc):
    return {'json_pointer': path, 'issue_type': kind, 'description': desc, 'status': 'open'}


def _normalise(raw):
    stats = raw.get('statistical_requirements', {})
    table = raw.get('table_requirements', {})
    if not isinstance(stats, dict):
        stats = {}
    if not isinstance(table, dict):
        table = {}
    stats = {
        **{k: stats.get(k) if isinstance(stats.get(k), str) else None for k in STAT_KEYS_STR},
        **{k: [x for x in stats.get(k, []) if isinstance(x, str) and x.strip()]
           if isinstance(stats.get(k), list) else [] for k in STAT_KEYS_ARR},
    }
    table = {
        **{k: [x for x in table.get(k, []) if isinstance(x, str) and x.strip()]
           if isinstance(table.get(k), list) else [] for k in TABLE_KEYS_ARR},
        'denominator_rule': table.get('denominator_rule')
        if isinstance(table.get('denominator_rule'), str) else None,
    }
    return {'statistical_requirements': stats, 'table_requirements': table}


def _drop_unsupported(data, unsupported):
    # Delete list items from highest index to lowest, avoiding index shifts.
    for path in sorted(set(unsupported), key=lambda s: (
        s.rsplit('/', 1)[0],
        -int(s.rsplit('/', 1)[1]) if s.rsplit('/', 1)[1].isdigit() else 0,
    )):
        parent, _, last = path.rpartition('/')
        try:
            if last.isdigit():
                seq = _get_pointer(data, parent)
                if int(last) < len(seq):
                    seq.pop(int(last))
            else:
                _set_pointer(data, path, None)
        except (KeyError, IndexError, TypeError, ValueError):
            pass


def _normal_text(text):
    text = unicodedata.normalize('NFKC', text).lower()
    text = re.sub(r'[\u2010-\u2015]', '-', text)
    return re.sub(r'[^a-z0-9%]+', ' ', text).strip()


def _listed_in_verified_quote(item, quote):
    """Very conservative check: whole normalized phrase or a documented alias.

    This is *not* an open-ended semantic entailment check. A quote merely
    mentioning the same topic is never enough to verify an unquoted list value.
    """
    value = _normal_text(item)
    quotation = _normal_text(quote)
    if not value or not quotation:
        return False
    aliases = {
        'sd': ['standard deviation', 'std deviation'],
        'min': ['minimum'], 'max': ['maximum'],
        'ci': ['confidence interval'],
        '95% ci': ['95% confidence interval', '95 confidence interval'],
        'frequency': ['frequencies'],
        'frequencies': ['frequency'],
    }
    candidates = [value] + aliases.get(value, [])
    return any(re.search(r'(?<![a-z0-9])' + re.escape(p) + r'(?![a-z0-9])', quotation)
               for p in candidates)


def _build_evidence(raw, data, candidates, sap):
    by_id = {b['block_id']: b for b in candidates}
    verified = {}  # original pointer -> list of (block ID, derivation, verified quote, note)
    issues = []
    for claim in raw.get('claims', []):
        if not isinstance(claim, dict):
            continue
        path = claim.get('json_pointer', '')
        block_id = claim.get('block_id')
        quote = claim.get('exact_quote', '')
        if not isinstance(path, str) or not path.startswith((
            '/statistical_requirements/', '/table_requirements/')):
            continue
        if not isinstance(quote, str) or not quote.strip() or block_id not in by_id or quote not in by_id[block_id]['text']:
            issues.append(_issue(path, 'unsupported', f'Unverified quote or block for {path}'))
            continue
        if claim.get('derivation') not in ('explicit', 'normalized'):
            issues.append(_issue(path, 'ambiguous', f'Inferred/unresolved claim for {path}'))
            continue
        try:
            value = _get_pointer(data, path)
        except (KeyError, IndexError, TypeError, ValueError):
            continue
        if not isinstance(value, str) or not value.strip():
            continue
        verified.setdefault(path, []).append((block_id, claim['derivation'], quote, None))

    present = list(_present_fields(data['statistical_requirements'], '/statistical_requirements'))
    present += list(_present_fields(data['table_requirements'], '/table_requirements'))

    # A group quotation can justify *additional* list members ONLY when the
    # specific full item is literally present in that exact, checked quotation.
    # We do not use other text from the same SAP block to fill gaps.
    for path in present:
        if path in verified:
            continue
        parent, _, index = path.rpartition('/')
        if not index.isdigit():
            continue
        try:
            item = _get_pointer(data, path)
        except (KeyError, IndexError, TypeError, ValueError):
            continue
        for cited_path, records in list(verified.items()):
            cited_parent, _, cited_idx = cited_path.rpartition('/')
            if cited_parent != parent or not cited_idx.isdigit():
                continue
            for block_id, _, quote, _ in records:
                if _listed_in_verified_quote(item, quote):
                    verified.setdefault(path, []).append((
                        block_id, 'normalized', quote,
                        'Item appears literally in a verified enumeration quotation.'
                    ))
                    break
            if path in verified:
                break

    unsupported = [path for path in present if path not in verified]
    for path in unsupported:
        issues.append(_issue(path, 'unsupported', 'Populated field without verifiable SAP quotation'))
    _drop_unsupported(data, unsupported)

    # Re-number provenance links after dropping unsupported list items.
    evidence = {}
    links = []
    for original_path, records in verified.items():
        if original_path in unsupported:
            continue
        parent, _, last = original_path.rpartition('/')
        path = original_path
        if last.isdigit():
            old = int(last)
            removed_before = sum(
                1 for p in unsupported
                if p.startswith(parent + '/') and p.rsplit('/', 1)[-1].isdigit()
                and int(p.rsplit('/', 1)[-1]) < old
            )
            path = parent + '/' + str(old - removed_before)
        ids = []
        for block_id, _, _, _ in records:
            b = by_id[block_id]
            evidence[block_id] = {
                'ref_id': block_id, 'document_kind': 'sap_body',
                'document_id': sap['filename'], 'page_numbers': [b['page']],
                'section': b['section'], 'exact_text': b['text'], 'location': block_id,
            }
            if block_id not in ids:
                ids.append(block_id)
        links.append({
            'json_pointer': path, 'ref_ids': ids,
            'derivation': ('explicit' if any(x[1] == 'explicit' for x in records)
                           else 'normalized'),
            'note': ('Item appears literally in a verified enumeration quotation.'
                     if any(x[3] for x in records) else None),
        })
    return list(evidence.values()), links, issues


def _is_descriptive_table(title):
    text = title.casefold().replace('-', ' ')
    return any(term in text for term in (
        'demograph', 'baseline characteristic', 'disposition', 'protocol deviation',
        'adverse event', 'safety summary', 'medical history', 'surgical history',
        'concomitant medication', 'prior medication', 'drug exposure',
        'treatment exposure', 'vital sign', 'ecg', 'ecog', 'hematology',
        'biochemistry', 'laboratory', 'physical exam',
    ))


def _explicit_population_in_title(title):
    title = title.lower().replace('-', ' ')
    if re.search(r'\b(intent\s+to\s+treat|itt)\b', title):
        return 'itt'
    if re.search(r'\b(per\s+protocol|pp\s+(?:population|analysis|set))\b', title):
        return 'pp'
    if 'safety analysis' in title or 'safety population' in title:
        return 'safety'
    return None


def _population_kind(value):
    text = value.lower().replace('-', ' ')
    if re.search(r'\b(intent\s+to\s+treat|itt)\b', text):
        return 'itt'
    if re.search(r'\b(per\s+protocol|pp)\b', text):
        return 'pp'
    if 'safety' in text:
        return 'safety'
    return None


def _apply_target_scope(tfl, data, links):
    """User-supplied explicit population suffix overrides generic multi-population SAP rules.

    Keep an auditable review issue when removing a supported but out-of-scope
    population, and maintain JSON pointer indices in field_links.
    """
    target = _explicit_population_in_title(tfl['title'])
    if not target:
        populations = {_population_kind(v) for v in data['statistical_requirements']['analysis_population']}
        populations.discard(None)
        if len(populations) > 1:
            return [_issue('/statistical_requirements/analysis_population', 'ambiguous',
                           'The target title does not identify one analysis population; '
                           'multiple SAP populations apply to related outputs. Confirm against the target Content List.')]
        return []
    path = '/statistical_requirements/analysis_population'
    values = data['statistical_requirements']['analysis_population']
    keep = [i for i, value in enumerate(values)
            if _population_kind(value) in (None, target)]
    removed = [i for i in range(len(values)) if i not in keep]
    if not removed:
        return []
    mapping = {old: new for new, old in enumerate(keep)}
    data['statistical_requirements']['analysis_population'] = [values[i] for i in keep]
    remapped = []
    for link in links:
        prefix = path + '/'
        old_path = link['json_pointer']
        if old_path.startswith(prefix) and old_path[len(prefix):].isdigit():
            old_index = int(old_path[len(prefix):])
            if old_index not in mapping:
                continue
            link = {**link, 'json_pointer': prefix + str(mapping[old_index])}
        remapped.append(link)
    links[:] = remapped
    return [_issue(path, 'ambiguous',
                   f'Removed {len(removed)} SAP-supported population(s) not matching '
                   f'the explicit target title ({target.upper()}); review table-specific scope.')]


def build_specification_from_extraction(tfl, sap, raw, candidates):
    """Pure post-processor; allows saved real LLM outputs to be replayed without API calls."""
    data = _normalise(raw)
    evidence, links, issues = _build_evidence(raw, data, candidates, sap)
    issues.extend(_apply_target_scope(tfl, data, links))
    descriptive = _is_descriptive_table(tfl['title'])
    optional_for_descriptive = {
        '/statistical_requirements/endpoint_name',
        '/statistical_requirements/endpoint_type',
        '/statistical_requirements/treatment_comparisons',
        '/statistical_requirements/visits_or_timepoints',
    }
    for item in raw.get('issues', []):
        if not isinstance(item, dict) or item.get('issue_type') not in (
            'missing', 'ambiguous', 'conflict', 'unsupported'):
            continue
        path = str(item.get('json_pointer', '/'))
        if descriptive and item['issue_type'] == 'missing' and path in optional_for_descriptive:
            # An inapplicable endpoint/test is not a failed extraction.
            continue
        issues.append(_issue(path, item['issue_type'], str(item.get('description', ''))))
    essentials = list(BASE_ESSENTIAL)
    if not descriptive:
        essentials.insert(0, ENDPOINT_ESSENTIAL)
    for path in essentials:
        try:
            value = _get_pointer(data, path)
        except (KeyError, IndexError, TypeError, ValueError):
            value = None
        if not value:
            issues.append(_issue(path, 'missing', 'Required for this target Table category'))
    if tfl.get('identification_source') == 'sap_heuristic_unverified':
        issues.append(_issue('/identity', 'ambiguous',
                             'SAP-only heuristic identification: confirm target TFL inventory'))
    blocked = any(not _get_pointer(data, path) for path in essentials)
    readiness = 'blocked' if blocked else ('needs_review' if issues else 'ready')
    spec = {
        'identity': {
            'tfl_id': tfl['tfl_id'], 'output_type': 'table', 'title': tfl['title'],
            'content_list_order': tfl['order'], 'section': None,
        },
        **data,
        'provenance': {'evidence': evidence, 'field_links': links},
        'issues': issues, 'readiness': readiness,
    }
    return spec


def build_specification(tfl, sap, llm, prompts_dir):
    prompts_dir = Path(prompts_dir)
    query_prompt = (prompts_dir / '01_query_plan.txt').read_text(encoding='utf-8')
    extract_prompt = (prompts_dir / '02_extract.txt').read_text(encoding='utf-8')
    generated = llm.json(query_prompt, json.dumps(tfl, ensure_ascii=False))
    queries = baseline_queries(tfl) + [str(q) for q in generated.get('queries', []) if isinstance(q, str)]
    index = SAPIndex(sap)
    candidates = index.search(queries, top_k=24)
    if not candidates:
        raise ValueError(f'No SAP evidence found for TFL {tfl["tfl_id"]}')
    prompt = json.dumps({'tfl': tfl, 'candidate_blocks': candidates}, ensure_ascii=False)
    raw = llm.json(extract_prompt, prompt)
    spec = build_specification_from_extraction(tfl, sap, raw, candidates)
    # One extra real LLM call ONLY when required fields were left blank.
    # Candidate sourcing and all repaired claims remain independently verified.
    from tfl_agent.agent.step2_completion import complete_required_fields
    spec, completion_audit = complete_required_fields(
        tfl, sap, llm, prompts_dir, raw, spec, candidates
    )
    return spec, {
        'queries': queries, 'candidates': candidates,
        'raw_extraction': raw, 'completion': completion_audit,
    }
