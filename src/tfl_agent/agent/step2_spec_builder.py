"""TFL requirements; no unsupported model claim may survive to the Specification."""
import json
from pathlib import Path
from tfl_agent.tools.sap_search import SAPIndex, baseline_queries

STAT_KEYS_STR=['analysis_topic','endpoint_name','endpoint_type']
STAT_KEYS_ARR=['analysis_population','analysis_methods','treatment_groups','treatment_comparisons',
               'visits_or_timepoints','statistics_to_display','variables_to_display',
               'stratification_factors','notes']
TABLE_KEYS_ARR=['row_requirements','column_requirements','footnote_requirements']
ESSENTIAL=['/statistical_requirements/endpoint_name','/statistical_requirements/analysis_population',
           '/statistical_requirements/analysis_methods','/statistical_requirements/treatment_groups',
           '/statistical_requirements/statistics_to_display','/table_requirements/row_requirements',
           '/table_requirements/column_requirements']

def _get_pointer(obj,ptr):
    node=obj
    for piece in ptr.strip('/').split('/'):
        piece=piece.replace('~1','/').replace('~0','~')
        node=node[int(piece)] if isinstance(node,list) else node[piece]
    return node

def _set_pointer(obj,ptr,value):
    parts=ptr.strip('/').split('/')
    node=obj
    for p in parts[:-1]:node=node[int(p)] if isinstance(node,list) else node[p]
    p=parts[-1]
    if isinstance(node,list):node[int(p)]=value
    else:node[p]=value

def _present_fields(section,base):
    for key,val in section.items():
        if isinstance(val,list):
            for idx,item in enumerate(val):
                if isinstance(item,str) and item.strip():yield f'{base}/{key}/{idx}'
        elif isinstance(val,str) and val.strip():yield f'{base}/{key}'

def _issue(path,kind,desc):
    return {'json_pointer':path,'issue_type':kind,'description':desc,'status':'open'}

def _normalise(raw):
    stats=raw.get('statistical_requirements',{})
    table=raw.get('table_requirements',{})
    stats={**{k:stats.get(k) if isinstance(stats.get(k),str) else None for k in STAT_KEYS_STR},
           **{k:[str(x) for x in stats.get(k,[]) if isinstance(x,str)] if isinstance(stats.get(k),list) else [] for k in STAT_KEYS_ARR}}
    table={**{k:[str(x) for x in table.get(k,[]) if isinstance(x,str)] if isinstance(table.get(k),list) else [] for k in TABLE_KEYS_ARR},
           'denominator_rule':table.get('denominator_rule') if isinstance(table.get('denominator_rule'),str) else None}
    return {'statistical_requirements':stats,'table_requirements':table}

def _drop_unsupported(data,unsupported):
    # Delete arrays backwards to preserve correct original indices.
    for path in sorted(set(unsupported),key=lambda s:(s.rsplit('/',1)[0],-int(s.rsplit('/',1)[1]) if s.rsplit('/',1)[1].isdigit() else 0)):
        parent,_,last=path.rpartition('/')
        try:
            if last.isdigit():
                seq=_get_pointer(data,parent)
                if int(last)<len(seq):seq.pop(int(last))
            else:_set_pointer(data,path,None)
        except (KeyError,IndexError,TypeError,ValueError):pass

def _build_evidence(raw,data,candidates,sap):
    by_id={b['block_id']:b for b in candidates}
    verified={}; issues=[]
    for claim in raw.get('claims',[]):
        if not isinstance(claim,dict):continue
        path=claim.get('json_pointer',''); block_id=claim.get('block_id'); quote=claim.get('exact_quote','')
        if not (path.startswith('/statistical_requirements/') or path.startswith('/table_requirements/')):continue
        if not isinstance(quote,str) or not quote.strip() or block_id not in by_id or quote not in by_id[block_id]['text']:
            issues.append(_issue(path,'unsupported',f'Unverified quote or block for {path}'))
            continue
        if claim.get('derivation') not in ('explicit','normalized'):
            issues.append(_issue(path,'ambiguous',f'Inferred/unresolved claim for {path}'))
            continue
        try: value=_get_pointer(data,path)
        except (KeyError,IndexError,TypeError,ValueError):continue
        if not (isinstance(value,str) and value.strip()):continue
        verified.setdefault(path,[]).append((block_id,claim['derivation']))
    present=list(_present_fields(data['statistical_requirements'],'/statistical_requirements'))
    present+=list(_present_fields(data['table_requirements'],'/table_requirements'))
    if data['table_requirements']['denominator_rule']:
        present.append('/table_requirements/denominator_rule')
    unsupported=[path for path in present if path not in verified]
    for path in unsupported: issues.append(_issue(path,'unsupported','Populated field without verifiable SAP quotation'))
    _drop_unsupported(data,unsupported)
    # Re-number list pointers after dropping unsupported items.
    evidence={}; links=[]
    for path,records in verified.items():
        if path in unsupported:continue
        parent,_,last=path.rpartition('/')
        # Derive correct index in a list whose unsupported original items were removed.
        if last.isdigit():
            old=int(last)
            removed_before=sum(1 for p in unsupported if p.startswith(parent+'/') and p.rsplit('/',1)[-1].isdigit() and int(p.rsplit('/',1)[-1])<old)
            path=parent+'/'+str(old-removed_before)
        ids=[]
        for bid,_ in records:
            b=by_id[bid]
            evidence[bid]={'ref_id':bid,'document_kind':'sap_body','document_id':sap['filename'],
                           'page_numbers':[b['page']],'section':b['section'],
                           'exact_text':b['text'],'location':bid}
            if bid not in ids:ids.append(bid)
        links.append({'json_pointer':path,'ref_ids':ids,
                      'derivation':'explicit' if any(x[1]=='explicit' for x in records) else 'normalized',
                      'note':None})
    return list(evidence.values()),links,issues

def build_specification(tfl,sap,llm,prompts_dir):
    prompts_dir=Path(prompts_dir)
    query_prompt=(prompts_dir/'01_query_plan.txt').read_text(encoding='utf-8')
    extract_prompt=(prompts_dir/'02_extract.txt').read_text(encoding='utf-8')
    generated=llm.json(query_prompt,json.dumps(tfl,ensure_ascii=False))
    queries=baseline_queries(tfl)+[str(q) for q in generated.get('queries',[]) if isinstance(q,str)]
    index=SAPIndex(sap)
    candidates=index.search(queries,top_k=24)
    if not candidates:raise ValueError(f'No SAP evidence found for TFL {tfl["tfl_id"]}')
    prompt=json.dumps({'tfl':tfl,'candidate_blocks':candidates},ensure_ascii=False)
    raw=llm.json(extract_prompt,prompt)
    data=_normalise(raw)
    evidence,links,issues=_build_evidence(raw,data,candidates,sap)
    for item in raw.get('issues',[]):
        if isinstance(item,dict) and item.get('issue_type') in ['missing','ambiguous','conflict','unsupported']:
            issues.append(_issue(str(item.get('json_pointer','/')),item['issue_type'],str(item.get('description',''))))
    for path in ESSENTIAL:
        try:value=_get_pointer(data,path)
        except KeyError:value=None
        if not value:issues.append(_issue(path,'missing','Required for safe MVP table generation'))
    if tfl.get('identification_source')=='sap_heuristic_unverified':
        issues.append(_issue('/identity','ambiguous','SAP-only heuristic identification: confirm target TFL inventory'))
    blocker=any(not _get_pointer(data,p) for p in ESSENTIAL)
    readiness='blocked' if blocker else ('needs_review' if issues else 'ready')
    spec={'identity':{'tfl_id':tfl['tfl_id'],'output_type':'table','title':tfl['title'],
                      'content_list_order':tfl['order'],'section':None},**data,
          'provenance':{'evidence':evidence,'field_links':links},'issues':issues,'readiness':readiness}
    return spec,{'queries':queries,'candidates':candidates,'raw_extraction':raw}
