"""Type-filtered keyword + structured metadata retrieval; embeddings can replace this backend."""
from tfl_agent.tools.sap_search import tokenize


def _index_keywords(idx,tid):
    if isinstance(idx,dict):
        values=idx.get('keyword_to_template_ids',idx.get('keyword_to_templates',idx))
        if isinstance(values,dict):
            return [str(k) for k,v in values.items() if isinstance(v,list) and tid in v]
    return []

def retrieve_templates(spec,library,top_k=5):
    stats=spec['statistical_requirements']
    req_endpoint=(stats['endpoint_name'] or '').lower()
    req_methods={m.lower() for m in stats['analysis_methods']}
    req_terms=set(tokenize(' '.join([spec['identity']['title'],stats['analysis_topic'] or '',req_endpoint]+stats['analysis_methods']+stats['statistics_to_display'])))
    matches=[]
    for t in library['templates']:
        ident=t['identity'];tid=ident['template_id']
        if ident.get('output_type')!=spec['identity']['output_type']:continue
        ctx=t.get('statistical_context',{})
        source_endpoint=(ctx.get('endpoint_name') or '').lower()
        context_text=(t.get('retrieval',{}).get('retrieval_text') or '')
        terms=[]
        terms+=t.get('retrieval',{}).get('keywords',[])+t.get('retrieval',{}).get('aliases',[])
        terms+=_index_keywords(library['index'],tid)
        terms+=[ident.get('normalized_title',''),ident.get('original_title',''),context_text,source_endpoint]
        template_terms=set(tokenize(' '.join(map(str,terms))))
        overlap=req_terms & template_terms
        lexical=len(overlap)/max(1,len(req_terms))
        endpoint_match=bool(req_endpoint and source_endpoint and req_endpoint==source_endpoint)
        method_match=bool(req_methods & {x.lower() for x in ctx.get('analysis_methods',[])})
        # Avoid silently using a template for a different explicitly documented endpoint.
        if source_endpoint and req_endpoint and source_endpoint!=req_endpoint and not endpoint_match:
            continue
        # Stronger weight on structure and endpoint than generic keyword overlap.
        score=round(0.45*int(endpoint_match)+0.3*int(method_match)+0.25*lexical,4)
        matches.append({'template_id':tid,'score':score,'matched_tokens':sorted(overlap),
                        'endpoint_match':endpoint_match,'method_match':method_match,
                        'source_path':t['resolved_path'],'template':t})
    matches.sort(key=lambda x:(-x['score'],x['template_id']))
    return matches[:top_k]

def select_template(matches,min_score=0.55):
    if not matches or matches[0]['score']<min_score:
        return None
    # Ambiguous top candidates must not be silently chosen.
    if len(matches)>1 and matches[0]['score']-matches[1]['score']<0.04:
        return None
    return matches[0]
