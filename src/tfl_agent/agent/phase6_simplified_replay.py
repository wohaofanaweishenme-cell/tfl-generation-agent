"""Phase 6.3.3.1: lossless partial replay; standard library only; no model calls."""
from __future__ import annotations
import csv, hashlib, json, zipfile, io
from pathlib import Path
from collections import Counter

ARCHIVE_NAME = '20261127T184942053899Z.zip'
ARCHIVE_SHA = '82ff0d60fe01ce8b3027eee46c5513e11d86086db8b6a723eb165a3c03e1fcfc'
APP = {'title_explicit','target_specific','general_study_context','topic_only','other_endpoint_or_output','insufficient_context','mixed'}
DISC = {'supports_candidate_over_alternative','does_not_distinguish','contradicts_candidate','uncertain'}
# Prospective contract: compare all templates, report only the ranked alternatives you can justify.
# No full ranking or per-citation prose is mandatory. No new pilot authorized.
SIMPLE_PROTOCOL = '''Compare every supplied same-type template using its structural_signature and not_for boundaries, not topic names. Distinguish target-specific SAP evidence from other endpoints and study context. Return JSON: ranking (nonempty ordered list of eligible IDs, best first, may be partial), recommended_template (first ID or null if no compatible template), supported_template (same as recommendation or null), selection_status (candidate_only, uncertain, no_compatible_template), proposed_preset (owned by recommendation or null), reason (decision explanation including unresolved competing structures), candidate_assessments (only ranked candidates, each template_id, compatibility, reason, missing_information, citations). Each citation: source, chunk_id (null for title), exact_quote, applicability, discrimination, competing_template, use. Citation reason optional; explain structural distinction at candidate level. Use structural_support only for target_specific or title_explicit evidence distinguishing a named competitor; counterevidence only for applicable contradiction. Non-discriminating, mixed and unrelated evidence is context. Do not assume absent statistics are ruled out. If material alternatives remain, supported_template=null. Never approve generation.'''

def nonempty(x): return isinstance(x,str) and bool(x.strip())
def sha(b): return hashlib.sha256(b).hexdigest()
def digest(obj): return sha(json.dumps(obj,ensure_ascii=False,separators=(',',':'),sort_keys=True).encode())

def normalize(obj,payload):
    """Report component validity independently; never fill missing ranks or reasons."""
    templates={t['template_id']:t for t in payload['library']['templates']}
    ids=set(templates); chunks={c['chunk_id']:c for c in payload['sap_evidence']}
    issues=[]; citations=[]; assessments={}
    def flag(x):
        if x not in issues: issues.append(x)
    if not isinstance(obj,dict): obj={}; flag('invalid_object')
    rank=obj.get('ranking'); rank_ok=isinstance(rank,list) and bool(rank) and all(nonempty(x) and x in ids for x in rank) and len(set(rank))==len(rank)
    order=list(rank) if rank_ok else []
    if not rank_ok: flag('invalid_rank_prefix')
    rec=obj.get('recommended_template'); sup=obj.get('supported_template'); status=obj.get('selection_status'); preset=obj.get('proposed_preset')
    if not all(k in obj for k in ('recommended_template','supported_template','selection_status','proposed_preset')): flag('missing_decision_fields')
    rec_ok=rank_ok and ((status=='no_compatible_template' and rec is None) or (status in ('candidate_only','uncertain') and rec==order[0]))
    if not rec_ok: flag('invalid_recommendation')
    if not nonempty(obj.get('reason')): flag('missing_decision_reason')
    if status not in ('candidate_only','uncertain','no_compatible_template') or (status=='candidate_only' and (sup is None or sup!=rec)) or (status!='candidate_only' and sup is not None): flag('invalid_support_status')
    owned={p['preset_id'] for p in templates.get(rec,{}).get('presets',[])} if isinstance(rec,str) else set()
    preset_ok=preset is None or (nonempty(preset) and preset in owned)
    if not preset_ok: flag('invalid_preset_ownership')
    raw_a=obj.get('candidate_assessments')
    if not isinstance(raw_a,list): raw_a=[]; flag('invalid_assessments')
    for a in raw_a:
        if not isinstance(a,dict) or not nonempty(a.get('template_id')) or a['template_id'] not in ids or a['template_id'] in assessments:
            flag('invalid_assessment_id'); continue
        tid=a['template_id']; assessments[tid]=a
        if a.get('compatibility') not in ('supported','uncertain','incompatible') or not nonempty(a.get('reason')): flag('invalid_assessment_fields')
        if not isinstance(a.get('missing_information'),list) or not all(isinstance(x,str) for x in a['missing_information']): flag('invalid_missing_information')
        cs=a.get('citations')
        if not isinstance(cs,list): flag('invalid_citation_array'); continue
        for i,c in enumerate(cs):
            errs=[]; c=c if isinstance(c,dict) else {}
            src,cid,q=(c.get(k) for k in ('source','chunk_id','exact_quote'))
            txt=payload['target']['title'] if src=='title' and cid is None and 'chunk_id' in c else chunks.get(cid,{}).get('text') if src=='sap' and isinstance(cid,str) else None
            exact=isinstance(txt,str) and nonempty(q) and q in txt
            if not exact: errs.append('invalid_exact_quote')
            app,disc,other,use=(c.get(k) for k in ('applicability','discrimination','competing_template','use'))
            if not isinstance(app,str) or app not in APP or (src=='title')!=(app=='title_explicit'): errs.append('invalid_applicability')
            if not isinstance(disc,str) or disc not in DISC: errs.append('invalid_discrimination')
            if disc in ('supports_candidate_over_alternative','contradicts_candidate'):
                if not nonempty(other) or other not in ids or other==tid: errs.append('invalid_competitor')
            elif other is not None: errs.append('unexpected_competitor')
            applicable=app in ('target_specific','title_explicit')
            if use=='structural_support' and (not applicable or disc!='supports_candidate_over_alternative'): errs.append('invalid_structural_support')
            elif use=='counterevidence' and (not applicable or disc!='contradicts_candidate'): errs.append('invalid_counterevidence')
            elif use not in ('structural_support','counterevidence','context'): errs.append('invalid_use')
            if errs: flag('citation_contract_error')
            citations.append({'template_id':tid,'citation_index':i,**c,'exact_match':bool(exact),'contract_valid':not errs,'issues':errs,'citation_reason_present':nonempty(c.get('reason')),'semantic_review':'unreviewed'})
    if not set(order)<=set(assessments): flag('missing_ranked_assessment')
    for tid,a in assessments.items():
        if a.get('compatibility')=='supported' and not any(c['template_id']==tid and c['contract_valid'] and c.get('use')=='structural_support' for c in citations): flag('supported_assessment_without_evidence')
    top=assessments.get(rec,{}) if isinstance(rec,str) else {}
    top_support=[c for c in citations if c['template_id']==rec and c['contract_valid'] and c.get('use')=='structural_support']
    if sup is not None and (top.get('compatibility')!='supported' or not top_support): flag('unsupported_declared_selection')
    hypothesis=obj.get('title_hypothesis')
    if hypothesis is not None:
        if not nonempty(hypothesis) or hypothesis not in ids: flag('invalid_title_hypothesis')
        elif rec is not None and rec!=hypothesis and not any(c.get('source')=='sap' and c.get('competing_template')==hypothesis for c in top_support): flag('unjustified_title_override')
    return {'rank_prefix':order,'rank_prefix_valid':bool(rank_ok),'complete_ranking':bool(rank_ok and set(order)==ids),'unranked_templates':sorted(ids-set(order)),
            'recommended_template':rec if rec_ok else None,'declared_supported_template':sup,'protocol_supported_template':sup if not issues and rec_ok and status=='candidate_only' else None,
            'proposed_preset':preset if preset_ok and rec_ok else None,'status':status,'reason':obj.get('reason'),'missing_information':top.get('missing_information',[]),
            'protocol_valid':not issues,'issues':issues,'citations':citations,'top_valid_structural_citations':len(top_support),'semantic_applicability_verified':False,'clinical_confirmation':False,'generation_authorized':False}

def load_archive(path):
    b=Path(path).read_bytes()
    if sha(b)!=ARCHIVE_SHA:
        with zipfile.ZipFile(io.BytesIO(b)) as outer:
            matches=[outer.read(n) for n in outer.namelist() if n.endswith('/'+ARCHIVE_NAME)]
        if len(matches)!=1 or sha(matches[0])!=ARCHIVE_SHA: raise ValueError('Frozen archive hash mismatch')
        b=matches[0]
    with zipfile.ZipFile(io.BytesIO(b)) as z:
        req=json.loads(z.read('Frozen_Requests.json')); raw=json.loads(z.read('Raw_Responses.json')); cfg=json.loads(z.read('Experiment_Config.json')); summary=json.loads(z.read('Summary.json')); labels=list(csv.DictReader(io.StringIO(z.read('Revised_Results.csv').decode('utf-8-sig'))))
    if len(req)!=6 or len(raw)!=6 or len(labels)!=6 or summary['new_attempts_reserved']!=6 or cfg['budget']!=6: raise ValueError('Unexpected six-attempt pilot')
    rr={r['request_id']:r for r in raw}; ll={r['request_id']:r for r in labels}; ri={r['request_id'] for r in req}
    if len(ri)!=6 or set(rr)!=ri or set(ll)!=ri: raise ValueError('Identity mismatch')
    for r in req:
        rid=r['request_id']; p=r['payload']; rec=rr[rid]
        fp=digest({'model':cfg['model'],'system':cfg['system'],'max_tokens':cfg['max_tokens'],'temperature':cfg['temperature'],'thinking':cfg['thinking'],'payload':p})
        if fp!=r['fingerprint'] or fp!=rec['fingerprint'] or rid!=f"{r['study_id']}__{r['entry_id']}__D_applicability": raise ValueError('Fingerprint mismatch')
        if ll[rid]['title']!=p['target']['title'] or ll[rid]['study_id']!=r['study_id'] or ll[rid]['entry_id']!=r['entry_id'] or ll[rid]['status']!=rec['status']: raise ValueError('Evaluation identity mismatch')
    return req,rr,ll,summary

def run_replay(path,out):
    req,raw,labels,old=load_archive(path); rows=[]; cites=[]; passages=[]; boundaries=[]
    for r in req:
        rid=r['request_id']; rr=raw[rid]; p=r['payload']; obj=json.loads(rr['raw_response']) if rr.get('finish_reason')=='stop' else None
        d=normalize(obj,p); expected=labels[rid]['expected']; ids=set(expected.split('|'))
        rank=next((i for i,t in enumerate(d['rank_prefix'],1) if t in ids),None)
        rows.append({'request_id':rid,'study_id':r['study_id'],'entry_id':r['entry_id'],'title':p['target']['title'],'expected':expected,'expected_rank_in_prefix':rank,'original_status':rr['status'],'original_error':rr.get('error'),**{k:v for k,v in d.items() if k!='citations'}})
        lookup={c['chunk_id']:c for c in p['sap_evidence']}
        for c in d['citations']:
            src=lookup.get(c.get('chunk_id'),{}) if isinstance(c.get('chunk_id'),str) else {}
            cites.append({'request_id':rid,'target_title':p['target']['title'],'section':src.get('section'),'context':src.get('text',p['target']['title'] if c.get('source')=='title' else None),**c})
        reviews=(obj or {}).get('passage_review',[]); review_map={x['chunk_id']:x for x in reviews if isinstance(x,dict) and isinstance(x.get('chunk_id'),str)}
        for cid,c in lookup.items(): passages.append({'request_id':rid,'chunk_id':cid,'section':c.get('section'),'text':c['text'],'model_review':review_map.get(cid),'semantic_review':'unreviewed'})
        # Show all considered template boundaries for a reviewer; never rewrite ranking using gold.
        for t in p['library']['templates']:
            tid=t['template_id']; boundaries.append({'request_id':rid,'target_title':p['target']['title'],'template_id':tid,'rank':d['rank_prefix'].index(tid)+1 if tid in d['rank_prefix'] else None,'structural_signature':t['structural_signature'],'not_for':t['not_for'],'model_assessment':next((a for a in (obj or {}).get('candidate_assessments',[]) if a.get('template_id')==tid),None),'semantic_review':'unreviewed'})
    def score(field):
        picked=sum(x[field] is not None for x in rows); correct=sum(x[field] in x['expected'].split('|') for x in rows)
        return {'selected':picked,'correct':correct,'incorrect':picked-correct,'coverage':picked/6,'accuracy_all':correct/6,'accuracy_selected':correct/picked if picked else None}
    ranks=[r['expected_rank_in_prefix'] for r in rows]; complete=[r for r in rows if r['complete_ranking']]
    report={'new_llm_calls':0,'source_archive_sha256':ARCHIVE_SHA,'historical_attempts':old['new_attempts_reserved'],'historical_usage':old['new_recorded_usage'],'n':6,'original_valid':sum(r['original_status']=='valid' for r in rows),'simplified_protocol_valid':sum(r['protocol_valid'] for r in rows),'complete_rankings':len(complete),'partial_rankings':sum(r['rank_prefix_valid'] and not r['complete_ranking'] for r in rows),'raw_prefix_top1':sum(i==1 for i in ranks),'prefix_recall_at_3_lower_bound':sum(i is not None and i<=3 for i in ranks)/6,'complete_ranking_top1_all':sum(r['expected_rank_in_prefix']==1 for r in complete)/6,'recommendation':score('recommended_template'),'declared_support':score('declared_supported_template'),'protocol_support':score('protocol_supported_template'),'citation_occurrences':len(cites),'exact_citations':sum(c['exact_match'] for c in cites),'contract_valid_citations':sum(c['contract_valid'] for c in cites),'missing_citation_reason':sum(not c['citation_reason_present'] for c in cites),'issues':dict(Counter(i for r in rows for i in r['issues'])),'semantic_review_complete':False,'generation_authorized':False,'caveat':'Retrospective protocol replay; partial ranks not filled; no independent semantic verification or new prompt experiment.'}
    out=Path(out); out.mkdir(parents=True,exist_ok=False)
    def save(name,value): (out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    save('Summary.json',report);save('Replayed_Decisions.json',rows);save('Citation_Audit.json',cites);save('Passage_Audit.json',passages);save('Library_Boundary_Audit.json',boundaries);(out/'Simplified_Protocol.txt').write_text(SIMPLE_PROTOCOL,encoding='utf-8')
    return report,rows
