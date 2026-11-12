"""Auditable source-template retrieval, not a model confidence estimator.

Use source-supported template family, title, statistics, methods and population.
A different known endpoint can be a *structural* candidate, never an
unreviewed automatic substitution for a target clinical endpoint.
"""
import re
import unicodedata
from tfl_agent.tools.sap_search import tokenize

STOP = {
    'a','an','and','as','at','based','by','each','for','from','in','is','of','on',
    'or','the','to','with','without','all','overall','patients','patient','subject',
    'subjects','summary','table','analysis','analyses','set','population','study',
    'total','number','percent','percentage','data',
}


def _normalize(text):
    return unicodedata.normalize('NFKC', str(text or '')).lower().replace('–','-').replace('—','-')


def _tokens(text):
    substitutions = {'demographic':'demographics','characteristic':'characteristics',
                     'measurements':'measurement','events':'event','rates':'rate',
                     'estimates':'estimate'}
    return {substitutions.get(w, w) for w in tokenize(_normalize(text))
            if w not in STOP and not w.isdigit() and len(w) >= 2}


def _similarity(a, b):
    """Dice coefficient on informative tokens; case/punctuation insensitive."""
    a, b = _tokens(a), _tokens(b)
    return 2 * len(a & b) / (len(a) + len(b)) if a and b else 0.0


def _family(title):
    """Family is inferred from the *output title*, never generic SAP context."""
    s = _normalize(title)
    if 'demograph' in s or 'baseline characteristic' in s:
        return 'demographics'
    if 'disposition' in s or 'withdrawal' in s:
        return 'disposition'
    if 'protocol deviation' in s:
        return 'protocol_deviations'
    if any(w in s for w in ('adverse event', 'teae', 'treatment-emergent', 'treatment emergent')):
        return 'adverse_events'
    if 'medical history' in s or 'surgical history' in s:
        return 'medical_history'
    if 'medication' in s or 'drug treatments' in s:
        return 'medications'
    if any(w in s for w in ('progression free survival', 'progression-free survival',
                            'overall survival', 'duration of response',
                            'time to progression', 'time-to-event', 'pfs time')) or re.search(r'\bpfs\b', s):
        return 'time_to_event'
    if any(w in s for w in ('objective response rate', 'clinical benefit rate', 'response rate', 'orr', 'cbr')):
        return 'response_rate'
    if any(w in s for w in ('treatment exposure', 'drug exposure', 'treatment duration', 'drug compliance')):
        return 'exposure'
    if any(w in s for w in ('hematology', 'biochemistry', 'laboratory')):
        return 'laboratory'
    if 'ecog' in s or 'performance status' in s:
        return 'performance_status'
    if 'ecg' in s or 'electrocardiogram' in s:
        return 'ecg'
    if 'vital sign' in s:
        return 'vital_signs'
    return None


def _endpoint_signature(title_or_endpoint):
    s = _normalize(title_or_endpoint)
    if 'progression free survival' in s or 'progression-free survival' in s or re.search(r'\bpfs\b', s):
        return 'pfs'
    if 'overall survival' in s or re.search(r'\bmedian os\b', s):
        return 'os'
    if 'duration of response' in s or re.search(r'\bdor\b', s):
        return 'dor'
    if 'time to progression' in s or re.search(r'\bttp\b', s):
        return 'ttp'
    if 'objective response rate' in s or re.search(r'\borr\b', s):
        return 'orr'
    if 'clinical benefit rate' in s or re.search(r'\bcbr\b', s):
        return 'cbr'
    return None


def _population_signature(text):
    s = _normalize(text).replace('-', ' ')
    if re.search(r'\b(itt|intent to treat)\b', s):
        return 'itt'
    if re.search(r'\b(pp|per protocol)\b', s):
        return 'pp'
    if 'safety analysis' in s or 'safety population' in s or 'safety set' in s:
        return 'safety'
    return None


def _statistics_features(text):
    s = _normalize(text)
    phrases = {
        'n': r'\b(n\b|count|frequency|frequencies|number of patients)',
        'percent': r'%|\b(percent|percentage|proportion)\b',
        'mean': r'\bmean\b',
        'sd': r'\b(sd|standard deviation)\b',
        'median': r'\bmedian\b',
        'min': r'\b(min|minimum)\b',
        'max': r'\b(max|maximum)\b',
        'ci': r'\b(ci|confidence interval|confidence limit|clopper.pearson)\b',
        'quartile': r'\b(q1|q3|quartile)\b',
        'event': r'\b(event|progression|death)\b',
        'censored': r'\bcensor',
    }
    return {name for name, pattern in phrases.items() if re.search(pattern, s)}


def _method_features(text):
    s = _normalize(text)
    methods = {
        'kaplan_meier': r'kaplan.?meier',
        'brookmeyer_crowley': r'brookmeyer.?crowley',
        'descriptive': r'descriptive|summary statistics',
        'frequency': r'\bfrequenc|\bproportion|\bpercent',
        'exact_binomial': r'exact.*binomial|clopper.?pearson',
    }
    return {name for name, pattern in methods.items() if re.search(pattern, s)}


def _index_keywords(idx, tid):
    if isinstance(idx, dict):
        values = idx.get('keyword_to_template_ids', idx.get('keyword_to_templates', idx))
        if isinstance(values, dict):
            return [str(k) for k, v in values.items() if isinstance(v, list) and tid in v]
    return []


def retrieve_templates(spec, library, top_k=5):
    stats = spec['statistical_requirements']
    title = spec['identity']['title']
    target_family = _family(title)
    target_endpoint = _endpoint_signature(stats.get('endpoint_name')) or _endpoint_signature(title)
    target_pop = _population_signature(title) or next(
        (_population_signature(p) for p in stats.get('analysis_population', []) if _population_signature(p)), None)
    target_methods = _method_features(' '.join(stats.get('analysis_methods', [])))
    target_stat = _statistics_features(' '.join(
        stats.get('statistics_to_display', []) + spec.get('table_requirements', {}).get('row_requirements', [])))
    target_terms = _tokens(' '.join([
        title, stats.get('analysis_topic') or '', stats.get('endpoint_name') or '',
    ] + stats.get('statistics_to_display', [])))

    matches = []
    for template in library['templates']:
        ident = template['identity']
        if ident.get('output_type') != spec['identity']['output_type']:
            continue
        tid = ident['template_id']
        ctx = template.get('statistical_context') or {}
        r = template.get('retrieval') or {}
        original_title = ident.get('normalized_title') or ident.get('original_title') or ''
        source_family = _family(original_title)
        if source_family is None:
            source_family = _family(ctx.get('analysis_topic') or '')
        # Never promote a clearly incompatible table family just because it
        # contains common words like "patients", "events" or "summary".
        if target_family and source_family and target_family != source_family:
            continue

        source_endpoint = (_endpoint_signature(ctx.get('endpoint_name'))
                           or _endpoint_signature(original_title))
        cross_endpoint = bool(target_endpoint and source_endpoint and target_endpoint != source_endpoint)
        endpoint_match = bool(target_endpoint and source_endpoint and target_endpoint == source_endpoint)

        source_methods = _method_features(' '.join(ctx.get('analysis_methods', [])))
        # Indexing text is source-authored and may describe the method even
        # when the structured method field is missing. Keep this auditable.
        retrieval_text = ' '.join(str(v) for v in (
            r.get('keywords', []) + r.get('aliases', []) + _index_keywords(library['index'], tid)
            + [r.get('retrieval_text') or '']
        ))
        source_methods |= _method_features(retrieval_text)
        source_pop = _population_signature(original_title) or next(
            (_population_signature(p) for p in ctx.get('analysis_population', []) if _population_signature(p)), None)
        source_spec = template.get('table_spec') or {}
        source_stat = _statistics_features(' '.join(
            [str(x) for x in source_spec.get('statistics', [])] +
            [str(row.get('statistic') or row.get('label') or '')
             for row in source_spec.get('rows', []) if isinstance(row, dict)] +
            [retrieval_text]
        ))

        title_similarity = _similarity(title, original_title)
        family_match = bool(target_family and target_family == source_family)
        if not target_family and not source_family and title_similarity >= 0.8:
            # Unknown but near-identical output titles have a useful signal.
            family_score = 0.35
        else:
            family_score = 0.45 * int(family_match)
        stat_similarity = (len(target_stat & source_stat) / len(target_stat)
                           if target_stat else 0.0)
        method_similarity = (len(target_methods & source_methods) / len(target_methods)
                             if target_methods else 0.0)
        population_match = bool(target_pop and source_pop and target_pop == source_pop)
        score = round(family_score + 0.27 * title_similarity + 0.13 * stat_similarity
                      + 0.10 * method_similarity + 0.05 * int(population_match), 4)

        template_terms = _tokens(' '.join([original_title, ctx.get('analysis_topic') or '',
                                           ctx.get('endpoint_name') or '', retrieval_text]))
        overlap = sorted(target_terms & template_terms)
        unknown = [k for k, v in [('endpoint', ctx.get('endpoint_name')),
                                  ('analysis_methods', ctx.get('analysis_methods', []))] if not v]
        reasons = [
            f'Table family: {source_family or "unknown"}' + (' (matched)' if family_match else ''),
            f'Title similarity: {title_similarity:.2f}',
            f'Statistics overlap: {len(target_stat & source_stat)}/{len(target_stat)} target feature(s)',
            f'Method overlap: {len(target_methods & source_methods)}/{len(target_methods)} target method(s)',
            f'Population: {source_pop or "unknown"}' + (' (matched)' if population_match else ''),
        ]
        if cross_endpoint:
            reasons.append('DIFFERENT KNOWN ENDPOINT: structural candidate only; manual review required')
        if target_pop and source_pop and not population_match:
            reasons.append('Population change needed during adaptation')
        reasons.append(f'Heuristic retrieval score={score:.4f}; NOT a model probability')
        matches.append({
            'template_id': tid, 'score': score, 'matched_tokens': overlap,
            'table_family': source_family, 'target_family': target_family,
            'title_similarity': round(title_similarity, 4),
            'statistics_match': round(stat_similarity, 4),
            'method_similarity': round(method_similarity, 4),
            'endpoint_match': endpoint_match, 'cross_endpoint': cross_endpoint,
            'method_match': bool(target_methods & source_methods),
            'population_match': population_match,
            'population_change_required': bool(target_pop and source_pop and not population_match),
            'requires_endpoint_review': cross_endpoint,
            'missing_library_fields': unknown,
            'source_study_id': template.get('source', {}).get('study_id'),
            'explanation': '; '.join(reasons),
            'source_path': template['resolved_path'], 'template': template,
        })

    matches.sort(key=lambda x: (-x['score'], x['template_id']))
    return matches[:top_k]


def template_selection_decision(matches, min_score=0.55, min_gap=0.04):
    """Separate BEST RANKED candidate from AUTOMATICALLY USABLE template.

    Retrieval is not clinical approval. Known population changes, endpoint
    changes and close competing candidates must be reviewed before generation.
    """
    if not matches:
        return {
            'status':'no_candidate', 'best_candidate_template_id':None,
            'selected_template_id':None, 'reasons':['No template candidates found'],
            'selection':None, 'requires_manual_review':True,
        }
    best = matches[0]
    score = best['score']
    reasons = []
    if score < min_score:
        status = 'retrieved_low_score'
        reasons.append(f'Top score {score:.4f} below required {min_score:.2f}')
    elif best.get('requires_endpoint_review') or best.get('cross_endpoint'):
        status = 'retrieved_needs_adaptation_review'
        reasons.append('Known target/source endpoints differ; statistics and footnotes require review')
    elif best.get('population_change_required'):
        status = 'retrieved_needs_adaptation_review'
        reasons.append('Analysis populations differ; denominator, headers, and footnotes require review')
    elif len(matches) > 1 and score - matches[1]['score'] < min_gap:
        status = 'retrieved_ambiguous'
        reasons.append(f'Top two template scores differ by less than {min_gap:.2f}')
    else:
        status = 'auto_selected'
        reasons.append('Top ranked candidate passed the configured retrieval gates')
    selection = best if status == 'auto_selected' else None
    return {
        'status':status,
        'best_candidate_template_id':best['template_id'],
        'selected_template_id':selection['template_id'] if selection else None,
        'reasons':reasons,
        'selection':selection,
        'requires_manual_review':selection is None,
    }


def select_template(matches, min_score=0.55):
    """Backward-compatible safe selection; None means NOT approved for generation."""
    return template_selection_decision(matches, min_score=min_score)['selection']
