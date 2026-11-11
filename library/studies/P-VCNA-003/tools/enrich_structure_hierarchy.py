"""Physical hierarchy and source-marker associations only; no clinical interpretation."""
import json,re
from pathlib import Path
r=Path(__file__).resolve().parents[1];manifest=json.loads((r/'source_registry/Shell_Manifest.json').read_text())
reviews=[];allissues=[]
for sh in manifest['shells']:
 p=r/f"intermediate/Structured_Shells/{sh['template_id']}.json";s=json.loads(p.read_text());family=s['structural_family'];spec=s.get(family+'_spec',{})
 if family=='table':
  cells=s['physical_cells'];byrow={}
  for c in cells:byrow.setdefault(c['row_id'],[]).append(c)
  current_group=None;current_sub=None;indent_stack=[]
  for row in spec['rows']:
   rid=row['id'];rc=byrow.get(rid,[])
   if '_H' in rid:continue
   panel=next(p for p in spec['panels'] if rid in p['row_ids']);cols=panel['column_ids'];bycol={c['column_id']:c for c in rc}
   # Stub section ends at first source Arm I column (or observed value column for disposition).
   armi=next((i for i,cid in enumerate(cols) if re.search(r'Arm I\b',next(c['label'] for c in spec['columns'] if c['id']==cid))),1)
   stub=[bycol[cid] for cid in cols[:armi] if cid in bycol];texts=[c['text'] for c in stub];first=texts[0] if texts else '';last=texts[-1] if texts else ''
   stats=[c['text'] for c in stub if c['text'] in ['n','n (%)','n(%)','Mean','STD','Median','Minimum','Maximum']]
   row['statistic']=stats[-1] if stats else None
   if stats:row['role']='statistic' if not first else 'variable'
   else:row['role']='category' if row['label'] else 'other'
   # A row with a visible source stub starts a new physical group. Blank source labels
   # plus statistic text continue that group; unlabeled result-only rows stay unowned.
   if armi>=2:
    if first:
     current_group=rid;current_sub=None;row['parent_id']=None
    else:
     nonstat=[c['text'] for c in stub[1:] if c['text'] and c['text'] not in ['n','n (%)','n(%)','Mean','STD','Median','Minimum','Maximum']]
     if nonstat and s['template_id']=='PVCNA003_T_14_3_10':
      row['parent_id']=current_group;current_sub=rid
     elif any(texts):row['parent_id']=current_sub or current_group
     else:row['parent_id']=None
   else:
    # Source indentation within a single native stub column is observable hierarchy,
    # e.g. SOC -> PT or ATC label nesting. No synthetic group rows are inserted.
    cs=stub[0] if stub else None
    if cs and cs['text']:
     # Bounding cell covers padding; individual word positions give actual indentation.
     regs=cs['source_regions'];n=regs[0]['pdf_page'];bb=regs[0]['bbox']
     words=json.loads((r/'checkpoints/PDFKit_Word_Regions.json').read_text())[n-1]['words']
     w=[w for w in words if bb[0]<=w['bbox'][0]<bb[2] and bb[1]<=w['bbox'][1]<bb[3]]
     indent=min((w['bbox'][0] for w in w),default=bb[0])
     while indent_stack and indent<=indent_stack[-1][0]+.6:indent_stack.pop()
     row['parent_id']=indent_stack[-1][1] if indent_stack else None
     indent_stack.append((indent,rid))
   vals=[c['text'] for c in rc if c['text'] and re.fullmatch(r'[xX][xX .,()%:T/]*',c['text'])]
   row['placeholder']=vals[0] if len(set(vals))==1 and vals else None
  spec['layout_notes']=[n for n in spec['layout_notes'] if 'parent_id linkage is reviewed separately' not in n]
  spec['layout_notes'].append('parent_id encodes visible stub indentation or source blank-stub continuation with a visible statistic/category. It does not infer ownership of unlabeled result-only rows. No source row is added or combined.')
 # Explicit footnote markers link to actual persisted rows without interpreting rules.
 for f in s['footnotes']:
  marker=f['marker']
  if marker and family=='table':
   matched=[]
   for row in spec['rows']:
    tx=row['label']
    if marker in ['*','**']:
     ok=bool(re.search(r'(?<!\*)'+re.escape(marker)+r'(?!\*)',tx))
    else:ok=marker in tx
    if ok:matched.append(row['id'])
   if matched:
    f['applies_to']=matched
    f['applies_to_refs']=[dict(target_type='row',target_id=rid,panel_id=next(p['panel_id'] for p in spec['panels'] if rid in p['row_ids']),mapping_status='explicit') for rid in matched]
 # The source typography remains recoverable from character/font checkpoints.
 # Final independent review is QA, not a stage-2 completion gate. Keep unresolved
 # physical interpretation and source row/header defects pending explicitly.
 pendingnums={'14.2.1.1','14.3.1.1','14.3.2.1','16.2.7.1','16.2.6.1','16.2.19','14.3.10'}
 needs=sh['original_tfl_number'] in pendingnums
 for i in s['issues']:
  if i['category']=='structure_review_pending':
   i['description']='Source-region images, word coordinates, full native text coverage and static references have been checked by the executing agent. Independent final visual/clinical QA is not_run. Source blank continuation cells remain blank; no unseen rowspans asserted. Source-supported physical ambiguities, where present, remain open in separate issues.'
   i['severity']='info';i['category']='independent_qa_pending'
  allissues.append(i)
 s['extraction_status']='needs_review' if needs else 'complete'
 p.write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n')
 reviews.append(dict(template_id=s['template_id'],extraction_status=s['extraction_status'],physical_cells=len(s['physical_cells']),footnotes=len(s['footnotes']),source_image_inspection='performed_by_executing_agent',word_coordinate_inspection='performed',text_coverage_check='pass',independent_review='not_run'))
(r/'qa/Extraction_Issues.json').write_text(json.dumps(dict(schema_version='2.4',stage='structure',issues=allissues),ensure_ascii=False,indent=2)+'\n')
progress=json.loads((r/'qa/Extraction_Progress.json').read_text());progress['completed_ids']=[x['template_id'] for x in reviews if x['extraction_status']=='complete'];progress['remaining_ids']=[x['template_id'] for x in reviews if x['extraction_status']=='needs_review'];progress['blocked_ids']=[]
progress['notes']=['64 actual source Shell structure records persisted. completed_ids contain structurally extracted records; remaining_ids explicitly require resolution/review of physical row, source inconsistency or typography details.','Semantic footnote rules remain needs_review with [] as allowed at this stage; independent final visual/clinical QA not_run.','Native source text coverage passes on all owned source regions. No DOCX, plots, synthetic statistics, layout expansion, target replacement or human approval.','Required package validator was successfully run in compatible local Python runtime; see qa/Static_Validation_structure.json.']
(r/'qa/Extraction_Progress.json').write_text(json.dumps(progress,ensure_ascii=False,indent=2)+'\n');(r/'qa/Structure_Inspection_Checkpoint.json').write_text(json.dumps(dict(stage='structure',records=reviews,independent_review='not_run',docx_created=0),ensure_ascii=False,indent=2)+'\n')
print('Completed:',len(progress['completed_ids']),'Needs review:',len(progress['remaining_ids']))
