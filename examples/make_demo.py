"""Create tiny SYNTHETIC test sources, not actual clinical trial evidence."""
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.pagesizes import letter
from docx import Document
from tfl_agent.tools.io_utils import write_json
from tfl_agent.tools.pdf_parser import parse_sap

pdf=ROOT/'input'/'synthetic_sap.pdf'
lines=[
    'SYNTHETIC SAP - FOR SOFTWARE TESTING ONLY',
    '4.1 Analysis Population',
    'The ITT population includes all randomized patients.',
    '4.2 Treatment Arms',
    'Subjects are assigned to Arm A or Arm B.',
    '6.4.1 Overall Survival',
    'Overall Survival (OS) is time from randomization to death from any cause.',
    'Overall survival will be analyzed using the Kaplan-Meier method.',
    'Median OS (months) and 95% CI will be reported by treatment arm.',
    'Table columns: Arm A and Arm B.',
    'Table rows: Median OS (months) and 95% CI.',
    'Footnote: Estimates are based on the Kaplan-Meier method.',
]
c=Canvas(str(pdf),pagesize=letter);c.setFont('Helvetica',11)
for i,line in enumerate(lines):c.drawString(48,742-47*i,line)
c.save()

file=ROOT/'library'/'templates'/'table'/'TBL_DEMO_OS.docx'
doc=Document()
doc.add_heading('{{TITLE}}',level=1)
doc.add_paragraph('Table {{TFL_ID}}')
tab=doc.add_table(rows=1,cols=3)
tab.style='Table Grid'
for j,text in enumerate(['Statistic','{{GROUP_1}}','{{GROUP_2}}']):tab.rows[0].cells[j].text=text
for text in ['{{STAT_1}}','{{STAT_2}}']:
    row=tab.add_row().cells
    for j,val in enumerate([text,'XX','XX']):row[j].text=val
doc.add_paragraph('{{FOOTNOTE_1}}')
doc.save(file)
meta={'library_id':'SYNTHETIC_DEMO_LIBRARY', 'templates':[{
    'identity':{'template_id':'TBL_DEMO_OS','output_type':'table','file_path':'table/TBL_DEMO_OS.docx',
                'original_tfl_number':'DEMO','original_title':'Summary of Overall Survival','normalized_title':'Summary of Overall Survival'},
    'source':{'study_id':'SYNTHETIC','sap_document_id':'SYNTHETIC_SAP'},
    'statistical_context':{'analysis_topic':'Overall Survival','endpoint_name':'Overall Survival',
                            'analysis_population':['ITT'],'analysis_methods':['Kaplan-Meier'],
                            'treatment_comparisons':[],'visits_or_timepoints':[]},
    'retrieval':{'keywords':['overall survival','OS','Kaplan-Meier','Median OS','95% CI'],
                 'aliases':['survival analysis'],
                 'retrieval_text':'Overall Survival table by treatment arm, Kaplan-Meier median OS and 95% CI'},
    'adaptation':{'editable_elements':[{'docx_locator':'{{TITLE}}','operation':'replace_text',
                 'element_type':'title','target_field':'/identity/title'}]},
    'footnotes':[{'category':'placeholder','exact_text':'{{FOOTNOTE_1}}'}],
}]}
write_json(ROOT/'library'/'metadata'/'Template_Metadata.json',meta)
write_json(ROOT/'library'/'index'/'Keyword_Index.json',
           {'keyword_to_template_ids':{'overall survival':['TBL_DEMO_OS'],'kaplan meier':['TBL_DEMO_OS']}})
write_json(ROOT/'library'/'Style_Guide.json',{'source':'synthetic-demo','permitted_defaults':[]})
write_json(ROOT/'examples'/'content_list.json',
           [{'tfl_id':'14.2.1','title':'Summary of Overall Survival','output_type':'table'}])

sap=parse_sap(pdf)
def block_containing(term):
    matches=[b for b in sap['blocks'] if term in b['text']]
    if not matches:raise RuntimeError('Missing expected synthetic term '+term)
    return matches[0]

stats={'analysis_topic':'Overall Survival','endpoint_name':'Overall Survival','endpoint_type':None,
    'analysis_population':['ITT'],'analysis_methods':['Kaplan-Meier'],
    'treatment_groups':['Arm A','Arm B'],'treatment_comparisons':[],
    'visits_or_timepoints':[],'statistics_to_display':['Median OS (months)','95% CI'],
    'variables_to_display':[],'stratification_factors':[],'notes':[]}
rows={'row_requirements':['Median OS (months)','95% CI'],
      'column_requirements':['Arm A','Arm B'],'denominator_rule':None,
      'footnote_requirements':['Estimates are based on the Kaplan-Meier method.']}
claims=[]
def claim(path,term):
    b=block_containing(term)
    claims.append({'json_pointer':path,'block_id':b['block_id'],'exact_quote':b['text'],'derivation':'explicit'})
claim('/statistical_requirements/analysis_topic','Overall Survival (OS)')
claim('/statistical_requirements/endpoint_name','Overall Survival (OS)')
claim('/statistical_requirements/analysis_population/0','ITT population')
claim('/statistical_requirements/analysis_methods/0','Kaplan-Meier method.')
claim('/statistical_requirements/treatment_groups/0','Subjects are assigned')
claim('/statistical_requirements/treatment_groups/1','Subjects are assigned')
claim('/statistical_requirements/statistics_to_display/0','Median OS (months)')
claim('/statistical_requirements/statistics_to_display/1','95% CI will be')
claim('/table_requirements/row_requirements/0','Table rows:')
claim('/table_requirements/row_requirements/1','Table rows:')
claim('/table_requirements/column_requirements/0','Table columns:')
claim('/table_requirements/column_requirements/1','Table columns:')
claim('/table_requirements/footnote_requirements/0','Footnote:')
write_json(ROOT/'examples'/'demo_llm_output.json',{
    '_warning':'Synthetic fixed outputs for deterministic tests, not SAP-derived LLM predictions.',
    'queries':['overall survival','ITT','treatment arms','median OS','Kaplan-Meier','footnote'],
    'extraction':{'statistical_requirements':stats,'table_requirements':rows,'claims':claims,'issues':[]}
})
print(f'Created synthetic SAP ({len(sap["blocks"])} blocks), table template, and fixture JSON.')
