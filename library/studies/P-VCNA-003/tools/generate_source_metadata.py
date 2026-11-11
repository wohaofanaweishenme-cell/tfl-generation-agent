"""v2.4 source metadata. All clinical text/structure comes from supplied SAP evidence.
Semantic interpretations below are agent-authored paraphrases of inspected source notes.
They are neither approved defaults nor target-study rules.
"""
import json,re,copy,hashlib,collections,shutil
from pathlib import Path
R=Path(__file__).resolve().parents[1];PACK=R.parent/'TFL_Extraction_Full_Package_v2_4'
CFG=json.loads((R/'Study_Run_Config.json').read_text());MAN=json.loads((R/'source_registry/Shell_Manifest.json').read_text());INV=json.loads((R/'source_registry/Study_Source_Inventory.json').read_text());EV=json.loads((R/'checkpoints/Source_Region_Evidence.json').read_text())['evidence'];PAGES=json.loads((R/'checkpoints/PDFKit_Page_Text.json').read_text());LINES=json.loads((R/'checkpoints/PDFKit_Line_Regions.json').read_text());SRC=INV['sources'][0];DID=SRC['document_id']
SNAP=R/'checkpoints/Metadata_Input_Snapshot';SNAP.mkdir(exist_ok=True)
# Preserve prior semantic state and locator inputs for reproducible parity checks.
for folder in ['intermediate/Structured_Shells','intermediate/DOCX_Locator_Map']:
 if not (SNAP/Path(folder).name).exists():shutil.copytree(R/folder,SNAP/Path(folder).name)
if not (R/'qa/Extraction_Progress.docx_snapshot.json').exists():shutil.copy2(R/'qa/Extraction_Progress.json',R/'qa/Extraction_Progress.docx_snapshot.json')

def norm(x):return re.sub(r'\s+',' ',x).strip()
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def stable(xs):return list(dict.fromkeys(xs))
def simple_reg(n,bb=None):
 p=PAGES[n-1];return dict(document_id=DID,pdf_page=n,bbox=bb or [0,0,p['width'],p['height']],coordinate_system='pdf_points_top_left')
def rule(typ,txt):return (typ,txt)
# Source-exact match dispatch, with no statistical completion from model knowledge.
def interpret(txt):
 t=norm(txt)
 if t.startswith('Percentage is the number of patients'):
  return [rule('denominator',t)]
 if t=='Patients who are lost to follow-up are censored at the time of their last visit or contact.':return [rule('missing_data',t)]
 if t.startswith('For each level of the ECOG score,'):
  return [rule('statistical_method','For each ECOG score level, the proportion of patients continuing on that or a better score is estimated for each visit using Kaplan-Meier estimates.'),rule('missing_data','At death, the patient is assumed to have risen to the highest ECOG score.')]
 if re.match(r'^(?:CS|NCS)\s*=',t):
  return [rule('abbreviation',a.strip().rstrip('.')+'.') for a in t.split(';') if a.strip()]
 if t.startswith('WHO-DDE version') or t.startswith('MedDRA version'):
  return [rule('coding_definition',t),rule('display_convention','The source retains the literal coding-version placeholder '+re.search(r'<[^>]+>',t)[0]+'.')]
 if t.startswith('Completed treatment refers'):
  return [rule('display_convention','Completed treatment refers to the completed treatment period.'),rule('display_convention','Completed study refers to the completed FU period.')]
 if t.startswith('Inclusion for subgroup analysis is defined'):
  return [rule('inclusion_exclusion','Arm I subgroup inclusion: patients had the first 3 cycles of SoC chemotherapy and started the 4th SoC chemotherapy.'),rule('inclusion_exclusion','Arm II subgroup inclusion: patients had the first 3 cycles of SoC chemotherapy, started the 4th cycle of SoC chemotherapy, and received 2 doses of VCN-01.')]
 if t in ['BSA = Body Surface Area.','PD = Progressive Disease.','TEAE = Treatment Emergent Adverse Event.','NA = Not applicable.']:return [rule('abbreviation',t)]
 if t.startswith('Yes = Treatment Emergent'):
  return [rule('coding_definition','Yes = Treatment Emergent for all study drugs.'),rule('coding_definition','Yes1 = Treatment Emergent for VCN-01.')]
 if t.startswith('Age was calculated'):
  return [rule('other','Age is calculated using Year of Birth and date of first treatment.'),rule('display_convention','Age is presented as age at last birthday.')]
 if t.startswith('BMI is the patient'):
  return [rule('other',t)]
 if t.startswith('Survival time is defined'):
  return [rule('other','Survival time is defined as time from randomization until death.'),rule('missing_data','Patients lost to follow-up are censored at the time of their last visit or contact.')]
 if t.startswith('Model terms include'):return [rule('statistical_method',t)]
 if t.startswith('* CMH') or t.startswith('** CMH'):return [rule('statistical_method',t.lstrip('* '))]
 if t.startswith('CR = Complete Response'):
  return [rule('abbreviation',a.strip().rstrip('.')+'.') for a in t.split(',')]
 if t.startswith('[a]:'):
  return [rule('display_convention','The marked source rows display number of events.'),rule('counting_rule','The marked source rows display number of patients with at least one event.'),rule('display_convention','The marked source rows display percentage of patients with at least one event.')]
 if t.startswith('[b]:'):return [rule('denominator','The denominator for each percentage in the marked dose-reduction reason section is the number of patients with dose reduction.')]
 if t.startswith('[c]:'):return [rule('other','Treatment compliance = percentage of injection administered (actual/planned).')]
 if t.startswith('Prior medications/medical procedures are defined'):
  return [rule('inclusion_exclusion','Prior medications: any medication taken within 28 days of the Screening visit.'),rule('inclusion_exclusion','Prior medical procedures: any medical procedures performed within 28 days of the Screening visit.')]
 if t.startswith('Data are summarized by:'):
  return [rule('display_convention',t)]
 if t.startswith('A patient with multiple occurrences'):
  return [rule('counting_rule','A patient with multiple occurrences of any AE is counted only once.'),rule('counting_rule','The source uses the maximum level of severity or the strongest relationship to study treatment.')]
 if t.startswith('The table presents number of patients'):
  return [rule('counting_rule','The table presents number of patients (n) who have at least one occurrence of the event.'),rule('display_convention','The table also presents percentage of patients.')]
 return []

ISSUES=[];SEM_REVIEW=[];templates=[]
ST={s['template_id']:json.loads((R/f"intermediate/Structured_Shells/{s['template_id']}.json").read_text()) for s in MAN['shells']}
# Direct source references for a potential time-origin inconsistency, kept unresolved.
os_st=ST['PVCNA003_T_14_2_1_1'];os_fn=os_st['footnotes'][0];os_el=next(e for e in os_st['source_elements'] if e['metadata_pointer']=='/footnotes/0/exact_text');os_ref=os_el['occurrences'][0]['source_ref_ids'][0]
fig_st=ST['PVCNA003_F_14_2_1'];fig_axis=next(b for b in fig_st['physical_blocks'] if 'x axis: Label: Time Post-Dose' in (b['exact_text'] or ''));fig_el=next(e for e in fig_st['source_elements'] if e['element_id']==fig_axis['source_element_ids'][0]);fig_ref=fig_el['occurrences'][0]['source_ref_ids'][0]
for sh in MAN['shells']:
 tid=sh['template_id'];st=ST[tid];lm=json.loads((R/f'intermediate/DOCX_Locator_Map/{tid}.json').read_text());family=st['structural_family'];spec=copy.deepcopy(st[family+'_spec']);assert st['source_elements']==lm['source_elements'];assert hashlib.sha256((R/'TFL_Template_Library'/lm['file_path']).read_bytes()).hexdigest()==lm['docx_boundary']['document_sha256']
 t=dict(identity=dict(template_id=tid,output_type=sh['output_type'],structural_family=family,file_path=lm['file_path'],original_tfl_number=sh['original_tfl_number'],original_title=sh['original_title'],normalized_title=norm(re.sub(r'\s*[–-]\s*\([12]\)$','',sh['original_title']))),source=dict(study_id=CFG['study_id'],clinicaltrials_id=None,sap_document_id=DID,sap_filename=Path(SRC['file_path']).name,sap_version=SRC['version'],shell_source_kind='other',shell_source_filename=Path(SRC['file_path']).name,shell_page_numbers=sorted(set(x['pdf_page'] for x in sh['source_regions'])),shell_section='15 SHELLS FOR TABLES, FIGURES AND LISTINGS',source_asset_path=SRC['file_path']),statistical_context={},retrieval={},adaptation=dict(required_sap_fields=[],editable_elements=[],permitted_defaults=[],adaptation_notes=[]),footnotes=copy.deepcopy(st['footnotes']),provenance=dict(evidence=[],field_links=[]),issues=[],quality=dict(review_status='pending',review_flags=['human_approval_pending','independent_semantic_review_not_run'],review_notes='Agent extraction from the supplied source only. Clinical/SAP definitions outside supplied pages are not inferred; no automatic approval.'),field_statuses=[],docx_boundary=copy.deepcopy(lm['docx_boundary']),source_elements=copy.deepcopy(lm['source_elements']),occurrence_relations=copy.deepcopy(lm['occurrence_relations']))
 t[family+'_spec']=spec;eref={}
 def add_ev(rid,regs,tx,kind='source_shell',record=tid,note=None,loc=None):
  if rid not in eref:
   item=dict(ref_id=rid,document_kind=kind,document_id=DID,page_numbers=sorted(set(x['pdf_page'] for x in regs)),location=loc or ('Physical PDF page/region in supplied '+Path(SRC['file_path']).name),exact_text=tx,source_record_id=record,source_regions=[{k:v for k,v in x.items() if k!='document_id'} for x in regs],notes=note)
   eref[rid]=item;t['provenance']['evidence'].append(item)
  return rid
 # Every actual source occurrence is tied to its existing region reference. Wrapper
 # occurrences are deliberately included, with their prior unlocated status unchanged.
 for e in t['source_elements']:
  for o in e['occurrences']:
   for rid in o['source_ref_ids']:add_ev(rid,EV[rid]['source_regions'],o['source_text'],note=EV[rid].get('note'))
 for f in t['footnotes']:
  el=next(e for e in t['source_elements'] if e['metadata_pointer']==f"/footnotes/{f['display_order']}/exact_text")
  for rid in f['evidence_ref_ids']:
   add_ev(rid,EV[rid]['source_regions'],f['exact_text'],note='Physical footnote region; source text unchanged.')
 # Scope of summary evidence is deliberately the real physical shell, not other
 # outputs mentioned in programming notes. Per-occurrence evidence remains precise.
 shellref=add_ev('SHELL_REGION',sh['source_regions'],None,note='Agent indexing aid: complete source regions. Exact native text is in per-occurrence evidence and Source_Record; not a clinical summary.')
 cover=add_ev('SAP_COVER',[simple_reg(1)],PAGES[0]['text'],kind='sap_body',record=None,note='Cover identity/version evidence only; not a SAP clinical/statistical definition.')
 section=add_ev('SOURCE_SECTION_15',[simple_reg(10)],PAGES[9]['text'],kind='sap_body',record=None,note='Retained source display instructions; not an approved style guide and not clinical analysis definitions.')
 def refs_for_block(b):
  return stable(r for e in t['source_elements'] if e['element_id'] in b['source_element_ids'] for o in e['occurrences'] for r in o['source_ref_ids'])
 own_title_blocks=[b for b in st['physical_blocks'] if b['kind']=='title'];title_refs=stable(r for b in own_title_blocks for r in refs_for_block(b)) or [shellref]
 def fstatus(ptr,status,refs,note):
  existing=next((x for x in t['field_statuses'] if x['json_pointer']==ptr),None)
  val=dict(json_pointer=ptr,status=status,evidence_ref_ids=stable(refs),note=note)
  if existing:existing.update(val)
  else:t['field_statuses'].append(val)
 def link(ptr,refs,derivation='explicit',note=None):t['provenance']['field_links'].append(dict(json_pointer=ptr,ref_ids=stable(refs),derivation=derivation,review_status='pending',note=note))
 def add_issue(ptr,cat,desc,refs,severity='warning'):
  t['issues'].append(dict(json_pointer=ptr,issue_type=cat,description=desc,source_ref_ids=stable(refs),status='open'))
  regs=[]
  for rr in refs:
   if rr in eref:regs.extend([dict(x,document_id=DID) for x in eref[rr].get('source_regions',[])])
  ISSUES.append(dict(issue_id=f'{tid}_MD{sum(x["template_id"]==tid for x in ISSUES)+1:03}',template_id=tid,severity=severity,category=cat,description=desc,status='open',source_regions=regs))
 # All supplied evidence, including real notes, is scanned for ID absence, but do
 # not manufacture an NCT identifier from the file name or external sources.
 assert not re.search(r'\bNCT\d{8}\b','\n'.join(p['text'] for p in PAGES))
 for key in ['template_id','output_type','structural_family','file_path','original_tfl_number','original_title']:
  fstatus('/identity/'+key,'explicit',title_refs if key not in ['template_id','file_path'] else [shellref],'Stable manifest/source identity; structural_family is the source-inspected layout, separate from source-declared output type.')
 fstatus('/identity/normalized_title','inferred',title_refs,'Agent normalization of whitespace and source panel suffix only; original_title is unchanged.');link('/identity/normalized_title',title_refs,'normalized')
 for key in ['study_id','sap_version','sap_document_id','sap_filename']:
  fstatus('/source/'+key,'explicit',[cover],'Supplied source identity and inventory; PDF filename is preserved.')
 fstatus('/source/clinicaltrials_id','not_found',[cover,shellref],'No NCT identifier found in the supplied 86-page PDF text. This is a bounded scan, not a claim about an unprovided full document.');link('/source/clinicaltrials_id',[cover,shellref],'unresolved')
 fstatus('/source/shell_source_kind','explicit',[section],'Shells are section 15 in the SAP; the source labels section 16 as appendices, so sap_appendix is not asserted.')
 for key in ['shell_source_filename','shell_page_numbers','shell_section','source_asset_path']:fstatus('/source/'+key,'explicit',[shellref,section],'Physical source document/page references, not printed page numbers.')
 # Direct display evidence excludes references to other layouts and wrapper text.
 main_blocks=[b for b in st['physical_blocks'] if b['kind'] not in ['programming_note','other']]
 main='\n'.join(b['exact_text'] or '' for b in main_blocks);main_norm=norm(main)
 def matching_refs(pattern,flags=re.I):return stable(r for b in main_blocks if re.search(pattern,b['exact_text'] or '',flags) for r in refs_for_block(b))
 body_cells=st['physical_cells'];col_labels=[c['label'] for c in spec.get('columns',[])];row_labels=[x['label'] for x in spec.get('rows',[]) if '_H' not in x['id']]
 pop=re.findall(r'\((All Randomized Set|Intent-to-Treat Set|Full Analysis Set|Safety Analysis Set|Pharmacodynamic Set|Per Protocol Set)\)',sh['original_title'])
 topic=re.sub(r'\s*\((?:All Randomized Set|Intent-to-Treat Set|Full Analysis Set|Safety Analysis Set|Pharmacodynamic Set|Per Protocol Set)\)','',t['identity']['normalized_title'])
 methods=[];methodrefs=[]
 for pattern,label in [(r'Kaplan[ -]Meier','Kaplan-Meier'),(r'Cox Proportional[-\s]*Hazards Model','Cox Proportional-Hazards Model'),(r'Log-rank test','Log-rank test'),(r'Cochran-Mantel-Haenszel \(CMH\) test','Cochran-Mantel-Haenszel (CMH) test')]:
  rr=matching_refs(pattern)
  if rr:methods.append(label);methodrefs+=rr
 # Preserve only the directly displayed groups, without importing context from a
 # referenced layout or assuming a formal contrast/model from side-by-side columns.
 arms=stable(norm(x) for x in col_labels if re.match(r'^Arm I',x))
 if family=='figure':arms=stable(x.split('– linestyle')[0].strip() for x in spec['legend_items'])
 visits=stable(c['text'] for c in body_cells if c['text'] in ['Screening','Baseline','<Visit>','Change from Baseline to <Visit>'])
 if '1-year Landmark' in sh['original_title']:visits.append('1-year Landmark')
 endpoint=None
 if sh['original_tfl_number'].startswith('14.2.') and sh['output_type']=='table':endpoint=re.sub(r'\s*[-–]\s*EDC Data$','',topic)
 if sh['output_type']=='figure' and 'Overall Survival' in topic:endpoint='Overall Survival'
 own_programs='\n'.join(x['exact_text'] for x in st['programming_notes'])
 source_context=''
 context_refs=[]
 if tid=='PVCNA003_T_14_5_1':
  source_context=' The source provides one panel for parameters assessed in both arms and a second for parameters applicable only to Arm II; the source note says to combine these two actual layouts in one output, starting each parameter on a new page.'
  context_refs=stable(rr for block in st['physical_blocks'] if block['kind']=='programming_note' for rr in refs_for_block(block))
 if tid=='PVCNA003_T_14_3_10':
  source_context=' The actual source note requests summaries by VCN-01, Nab-paclitaxel and Gemcitabine, and excludes the dose-reduction category for VCN-01 administration. This is retained source context, not a target-study action.'
  context_refs=stable(rr for block in st['physical_blocks'] if block['kind']=='programming_note' for rr in refs_for_block(block))
 t['statistical_context']=dict(analysis_topic=topic,endpoint_name=endpoint,endpoint_type=None,analysis_population=stable(pop),analysis_methods=methods,treatment_comparisons=arms,visits_or_timepoints=stable(visits),applicable_context='Agent summary of source display: '+topic+'. This records the source shell only; no target-study eligibility or SAP analysis hierarchy is inferred.'+source_context,not_applicable_context=[])
 for key,val in t['statistical_context'].items():
  refs=methodrefs if key=='analysis_methods' and methods else matching_refs(r'Arm I') if key=='treatment_comparisons' and arms else title_refs if key in ['analysis_topic','endpoint_name','analysis_population'] else [shellref]
  refs=(refs+context_refs) if key=='applicable_context' else refs
  status='inferred' if key=='applicable_context' else 'not_found' if val is None or val==[] else 'explicit'
  note='Source display only; no unprovided SAP definition or target requirement is asserted.'
  if key=='endpoint_type':note='No explicit endpoint-type classification extracted from the supplied shell; not inferred from method/name.'
  if key=='not_applicable_context':note='No explicit exclusion-of-use context supplied; [] is not a declaration of universal applicability.'
  if key=='treatment_comparisons':note='Actual displayed source arm/legend labels only; no additional formal contrast inferred.'
  if key=='analysis_population' and not pop:note='No analysis-population declaration in this actual shell title; not inferred from topic or other shells.'
  fstatus('/statistical_context/'+key,status,refs or [shellref],note);link('/statistical_context/'+key,refs or [shellref],'inferred' if status=='inferred' else 'unresolved' if status=='not_found' else 'explicit',note)
 if family=='listing':
  for key in ['record_unit','sort_by','filters_or_inclusion_rules']:
   fstatus('/listing_spec/'+key,'not_found',[shellref],'Source row/column layout preserved; record unit, sorting and input filters are not inferred from column names.')
  for i,c in enumerate(spec['columns']):fstatus(f'/listing_spec/columns/{i}/source_variable','not_found',[shellref],'No SDTM/ADaM/source variable name was explicitly supplied.')
 if family=='figure':
  for i,panel in enumerate(spec['panels']):
   for ax in ['x_axis','y_axis']:
    for key,value in panel[ax].items():fstatus(f'/figure_spec/panels/{i}/{ax}/{key}','not_found' if value is None else 'explicit',matching_refs(r'(?:x axis|Y axis)') or [shellref],'Axis fields copied from actual textual source specification; unspecified units/scales stay null.')
 if family=='table':fstatus('/table_spec/denominator_rule','unreviewed',[shellref],'Kept null deliberately; source denominators remain separate footnote semantic rules and scopes, not flattened into a global default.')
 # Every physical note is preserved; clauses are independent, source-supported
 # summaries. Scope overrides narrow a rule without altering the physical note scope.
 for i,f in enumerate(t['footnotes']):
  meanings=interpret(f['exact_text']);f['semantic_rules']=[]
  for j,(kind,statement) in enumerate(meanings):
   rr=dict(rule_id=f"{f['footnote_id']}_RULE{j+1:02}",rule_type=kind,normalized_rule=statement,rule_status='explicit',adaptation_field=None,evidence_ref_ids=f['evidence_ref_ids'][:])
   overrides=[]
   if kind=='denominator' and f['exact_text'].startswith('Percentage is the number of patients'):
    for cell in body_cells:
     if cell['text'] and '%' in cell['text'] and not '_H' in cell['row_id']:
      # Dose-reduction reasons have their own [b] denominator. Do not apply
      # the general rule to those source row bands, even for this summary.
      if tid=='PVCNA003_T_14_3_10' and cell['row_id'] in ['P02_R005','P02_R006','P02_R007']:continue
      overrides.append(dict(target_type='cell',target_id=cell['row_id']+':'+cell['column_id'],panel_id=cell['panel_id'],mapping_status='inferred'))
   elif f['marker'] in ['[a]','[b]','[c]']:
    # Marker row scope retained exactly; additional visible continuations are
    # separately inferred rule scope, never a change to the physical footnote.
    base=[x['target_id'] for x in f['applies_to_refs'] if x['target_type']=='row']
    expand={'[a]':['P01_R022','P01_R023','P02_R001','P02_R002','P02_R003','P02_R004','P02_R005','P02_R006','P02_R007'],'[b]':['P02_R005','P02_R006','P02_R007'],'[c]':['P02_R008','P02_R009','P02_R010','P02_R011','P02_R012']}[f['marker']]
    for rowid in expand:
     if any(x['id']==rowid for x in spec.get('rows',[])):overrides.append(dict(target_type='row',target_id=rowid,panel_id=next(p['panel_id'] for p in spec['panels'] if rowid in p['row_ids']),mapping_status='explicit' if rowid in base else 'inferred'))
   if overrides:rr['applies_to_refs']=overrides
   f['semantic_rules'].append(rr)
  f['semantic_extraction_status']='extracted' if meanings else 'needs_review'
  SEM_REVIEW.append(dict(template_id=tid,footnote_id=f['footnote_id'],source_text_sha256=hashlib.sha256(f['exact_text'].encode()).hexdigest(),semantic_extraction_status=f['semantic_extraction_status'],rules=len(meanings),interpretation='agent-authored faithful source paraphrase; not an approved default',physical_scope_unchanged=True))
  fstatus(f'/footnotes/{i}/semantic_rules','explicit' if meanings else 'unreviewed',f['evidence_ref_ids'],'Agent-authored clause paraphrases from the inspected physical footnote. Explicit source statements do not imply independently approved scopes.');link(f'/footnotes/{i}/semantic_rules',f['evidence_ref_ids'],'normalized')
  if any(x['mapping_status']=='unresolved' for x in f['applies_to_refs']):
   fstatus(f'/footnotes/{i}/applies_to_refs','unreviewed',f['evidence_ref_ids'],'Physical source scope remains unresolved from stage 2. Rule-level source-supported scope suggestions do not overwrite it.')
   add_issue(f'/footnotes/{i}/applies_to_refs','ambiguous','Physical footnote applicability remains unresolved. Rule text is extracted; any rule-specific inferred scope is separately marked.',f['evidence_ref_ids'])
  else:fstatus(f'/footnotes/{i}/applies_to_refs','explicit',f['evidence_ref_ids'],'Exact existing marker-to-row physical scope copied without alteration.')
  if not meanings:add_issue(f'/footnotes/{i}/semantic_rules','ambiguous','Inspected physical footnote could not be fully interpreted without assumptions.',f['evidence_ref_ids'])
 # Faithful source-only keywords/aliases. Terms are added only when present in
 # this shell's own title/body/notes, not from referenced or missing shells.
 keywords=[topic,sh['output_type']];aliases=[];kwrefs=title_refs[:]
 for method in methods:keywords.append(method)
 pairs=[('ORR','Objective Response Rate'),('DCR','Disease Control Rate'),('CR','Complete Response'),('PR','Partial Response'),('SD','Stable Disease'),('BSA','Body Surface Area'),('PD','Progressive Disease'),('TEAE','Treatment Emergent Adverse Event'),('NCS','Not Clinically Significant'),('CS','Clinically Significant'),('NA','Not applicable'),('OS','Overall Survival'),('PFS','Progression'),('TTP','Time to Progression'),('DoR','Duration of Response')]
 for ab,long in pairs:
  if re.search(r'\b'+re.escape(ab)+r'\b',main_norm) and long.lower() in main_norm.lower():aliases.append(ab);keywords.append(long);kwrefs+=matching_refs(r'\b'+re.escape(ab)+r'\b')
 if 'EDC Data' in topic and 'Electronic Data Capture' in own_programs:
  aliases.append('EDC');keywords.append('Electronic Data Capture')
  kwrefs+=stable(rr for block in st['physical_blocks'] if block['kind']=='programming_note' and 'Electronic Data Capture' in (block['exact_text'] or '') for rr in refs_for_block(block))
 concepts=[]
 for f in t['footnotes']:
  for rulex in f['semantic_rules']:
   k=rulex['rule_type'];tx=rulex['normalized_rule']
   if k=='denominator':concepts.append('percentage denominator');keywords.append('percentage denominator')
   elif k=='missing_data' and 'censor' in tx.lower():concepts.append('censoring at last visit or contact');keywords.append('censoring')
   elif k=='statistical_method' and 'stratified' in tx:concepts.append(tx);keywords.append('stratification')
   elif k=='counting_rule':concepts.append(tx);keywords.append('patient/event counting')
   elif k=='coding_definition' and 'version' in tx:keywords.append(tx.split(' version')[0]);concepts.append(tx)
   elif f['marker']=='[b]':concepts.append(tx);keywords.append('dose reduction denominator')
   elif f['marker']=='[c]':concepts.append(tx);keywords.append('treatment compliance')
  kwrefs+=f['evidence_ref_ids']
 # Ensure the exceptional denominator is always prominent, not truncated out of
 # compact retrieval text by more general count/display concepts.
 if tid=='PVCNA003_T_14_3_10':concepts=['General percentage denominator is column N, except where otherwise specified; dose-reduction reason percentages use patients with dose reduction.','Marked rows distinguish events, patients with events, and percentages; compliance is actual/planned injections.'];keywords+=['dose reduction denominator','events','patients with events','actual/planned injections']
 retrieval='Agent summary: '+sh['output_type'].capitalize()+' '+sh['original_tfl_number']+'; '+topic+'. '
 if family=='figure':retrieval+='Source textual figure specification; no plotted data or executable program. '
 elif family=='listing':retrieval+='Displays '+', '.join(stable(norm(x) for x in col_labels if x)[:8])+'. '
 else:retrieval+='Source display includes '+', '.join(stable(spec['statistics'])[:8])+'. ' if spec['statistics'] else 'Source rows and arm columns retained. '
 if pop:retrieval+='Population: '+', '.join(pop)+'. '
 if concepts:retrieval+='Source note concepts: '+'; '.join(x.rstrip('.') for x in stable(concepts)[:4])+'.'
 t['retrieval']=dict(keywords=stable(x for x in keywords if x),aliases=stable(aliases),retrieval_text=retrieval.strip())
 for key in ['keywords','aliases','retrieval_text']:
  fstatus('/retrieval/'+key,'inferred',stable(kwrefs+methodrefs),'Agent source-supported indexing summary/selection, not additional clinical facts.');link('/retrieval/'+key,stable(kwrefs+methodrefs),'normalized','No embeddings, ranking algorithm or retrieval contract generated.')
 for key in t['adaptation']:fstatus('/adaptation/'+key,'not_applicable',[],'Outside this source extraction phase; no approved Style Guide or target adaptation request. Arrays intentionally remain empty.')
 # Preserve source display vs SAP definition boundaries and existing source issues.
 add_issue('/statistical_context','missing','Original printed SAP pages 4–29 are absent from the supplied PDF. Retained source body provides no corresponding full statistical analysis definitions; this metadata records shell display statements only.',[cover,section,shellref],'info')
 for old in st['issues']:
  if old['category'] in ['independent_qa_pending','footnote_scope_pending']:continue
  ptr='/'+family+'_spec';cat='conflict' if old['category']=='source_row_header_mismatch' else 'ambiguous'
  add_issue(ptr,cat,old['category']+': '+old['description'],[shellref]);t['quality']['review_flags'].append(old['category'])
 if st['extraction_status']=='needs_review':t['quality']['review_flags'].append('source_structure_pending')
 if any(x['docx_locator'] is None for e in t['source_elements'] for x in e['occurrences']):t['quality']['review_flags'].append('documented_wrapper_exclusions_unlocated')
 if any(x['issue_type']=='ambiguous' and x['json_pointer'].startswith('/footnotes/') for x in t['issues']):t['quality']['review_flags'].append('physical_footnote_scope_pending')
 if tid in ['PVCNA003_T_14_2_1_1','PVCNA003_F_14_2_1']:
  add_ev(os_ref,EV[os_ref]['source_regions'],os_fn['exact_text'],record='PVCNA003_T_14_2_1_1',note='Source OS table definition; not a missing SAP-body definition.')
  add_ev(fig_ref,EV[fig_ref]['source_regions'],fig_axis['exact_text'],record='PVCNA003_F_14_2_1',note='Actual source OS figure axis label.')
  ptr='/figure_spec/panels/0/x_axis/label' if family=='figure' else '/footnotes/0/semantic_rules/0'
  add_issue(ptr,'conflict','Potential source time-origin inconsistency: the OS figure labels its x axis Time Post-Dose (months), while the OS table defines survival from randomization until death. Both source statements retained; no preferred definition inferred.',[os_ref,fig_ref]);fstatus(ptr,'conflicting',[os_ref,fig_ref],'Source-shell statements differ; no SAP-body resolution is available in supplied pages.');t['quality']['review_flags'].append('source_time_origin_conflict')
 if tid=='PVCNA003_F_14_2_1':
  # Both literal sides of the source reference-number conflict are persisted.
  dr=next(x for x in MAN['content_list_mappings'] if x['source_document_id']==DID and x['original_tfl_number']=='14.2.6' and x['original_title'].startswith('Kaplan'))
  cref=add_ev('DIRECTORY_FIG_14_2_6',[simple_reg(8)],'Figure 14.2.6 '+dr['original_title'],kind='sap_body',record=None,note='Section 14.2 directory, not SAP statistical definition.')
  note=next(b for b in st['physical_blocks'] if 'Programming note for Figure 14.2.6' in (b['exact_text'] or ''));nrefs=refs_for_block(note)
  add_issue('/figure_spec','conflict','Source directory calls Figure 14.2.6 Progression Free Survival; source programming note calls Figure 14.2.6 Duration of Response. This remains a source note only, not an expanded/new shell.',[cref]+nrefs);t['quality']['review_flags'].append('source_reference_number_conflict')
 if tid in ['PVCNA003_T_14_1_2_1','PVCNA003_L_16_2_4_1']:
  entry=next(x for x in MAN['content_list_mappings'] if x['original_tfl_number']==sh['original_tfl_number'] and x['source_document_id']==DID);n=4 if sh['output_type']=='table' else 8
  rid=add_ev('DIRECTORY_TITLE_VARIANT',[simple_reg(n)],entry['original_title'],kind='sap_body',record=None,note='Literal Content List title variant; actual Shell title is authoritative for identity.original_title.')
  add_issue('/identity/original_title','conflict','Content List and physical shell differ in Demographic/Demographics wording. Both preserved; original_title remains the actual physical shell title.',[rid]+title_refs,'info');fstatus('/identity/original_title','conflicting',[rid]+title_refs,'Physical shell wording retained; directory variant recorded separately without silent normalization.')
 t['quality']['review_flags']=stable(t['quality']['review_flags']);fstatus('/quality/review_status','explicit',[],'Pending by workflow; no authorized human approval record exists.')
 # Specs/locators are verbatim copies; semantic enrichment does not rewrite DOCX.
 fstatus('/docx_boundary','explicit',[shellref],'Actual Locator Map boundary/hash copied unchanged, previously checked in document.xml.');link('/'+family+'_spec',[shellref],'explicit','Exact Structured_Shell specification copy.');link('/source_elements',[shellref],'explicit','Exact Locator Map copy, including repeated and documented unlocated wrapper occurrences.')
 for i,f in enumerate(t['footnotes']):
  # Semantic fields enriched in the structure layer too; physical text/scope/IDs unchanged.
  for k in ['semantic_rules','semantic_extraction_status']:st['footnotes'][i][k]=copy.deepcopy(f[k])
 write(R/f'intermediate/Structured_Shells/{tid}.json',st)
 templates.append(t)
write(R/'Study_Metadata.json',dict(schema_version='2.4',library_id=CFG['library_id'],templates=templates))
write(R/'qa/Metadata_Issues.json',dict(schema_version='2.4',stage='metadata',issues=ISSUES));write(R/'qa/Footnote_Semantic_Extraction.json',dict(note='Agent-authored clause interpretation of inspected supplied source only; physical notes and scopes are unchanged.',records=SEM_REVIEW))
write(R/'qa/Metadata_Completed_Record_Index.json',[dict(template_id=t['identity']['template_id'],file_path=t['identity']['file_path'],quality=t['quality']['review_status'],source_structure_status=ST[t['identity']['template_id']]['extraction_status'],semantic_rules=sum(len(f['semantic_rules']) for f in t['footnotes'])) for t in templates])
p=json.loads((R/'qa/Extraction_Progress.json').read_text());p['stage']='metadata';pending={s['template_id'] for s in ST.values() if s['extraction_status']=='needs_review'}|{'PVCNA003_F_14_2_1'};p['completed_ids']=[x for x in p['manifest_ids'] if x not in pending];p['remaining_ids']=[x for x in p['manifest_ids'] if x in pending];p['blocked_ids']=[];p['full_study_complete']=False;p['notes']=['64 actual-source Metadata records written, each linked to an existing DOCX and copied Locator Map. Metadata presence is not approval.','56 records complete current extraction; 8 remain for physical/source review (prior 7 plus OS figure potential time-origin conflict). All 64 quality.review_status=pending.','Shell display statements distinguished from unprovided SAP analysis definitions. All 73 physical footnotes preserved with their original typed scopes; source-supported semantic clauses enriched separately.','DOCX bytes, boundaries and occurrence locators unchanged. No target adaptation/defaults/embeddings/retrieval contract; required_sap_fields, editable_elements, permitted_defaults remain [].'];write(R/'qa/Extraction_Progress.json',p)
shutil.copy2(PACK/'prompts/04_Generate_Metadata.txt',R/'checkpoints/Instructions/04_Generate_Metadata.txt')
print(json.dumps(dict(metadata_records=len(templates),physical_footnotes=sum(len(t['footnotes']) for t in templates),semantic_rules=sum(len(f['semantic_rules']) for t in templates for f in t['footnotes']),footnote_statuses=dict(collections.Counter(f['semantic_extraction_status'] for t in templates for f in t['footnotes'])),quality_statuses=dict(collections.Counter(t['quality']['review_status'] for t in templates)),completed=len(p['completed_ids']),remaining=len(p['remaining_ids']),issues=len(ISSUES)),indent=2))
