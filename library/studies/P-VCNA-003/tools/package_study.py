#!/usr/bin/env python3
"""Checkpoint packaging; never grants approval or generates source content."""
import argparse,json,pathlib,sys,zipfile
from validate_study import Validator

def package(root,output,stage=None,allow_errors=False):
 root=pathlib.Path(root).resolve();output=pathlib.Path(output).resolve()
 if output.is_relative_to(root):raise ValueError('Output ZIP must be outside the Study directory.')
 progress=json.loads((root/'qa/Extraction_Progress.json').read_text());stage=stage or progress['stage']
 report=Validator(root,stage).run()
 if report['errors'] and not allow_errors:raise ValueError('Static validation failed; fix errors or explicitly use --allow-errors to preserve an invalid checkpoint.')
 incomplete=not progress['full_study_complete'] or bool(report['errors'])
 if incomplete:output=output.with_name(output.stem+'_INCOMPLETE_CHECKPOINT.zip')
 elif output.suffix.lower()!='.zip':output=output.with_suffix('.zip')
 output.parent.mkdir(parents=True,exist_ok=True)
 reportname='qa/Checkpoint_Static_Validation.json'
 with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
  for p in sorted(root.rglob('*')):
   if p.is_symlink():raise ValueError('Symlink is not allowed in Study package: '+str(p))
   if not p.is_file() or '__pycache__' in p.parts or '.git' in p.parts or p.name=='.DS_Store':continue
   name=p.relative_to(root).as_posix()
   if name!=reportname:z.write(p,name)
  z.writestr(reportname,json.dumps(report,ensure_ascii=False,indent=2)+'\n')
  z.writestr('CHECKPOINT_STATUS.txt','Incomplete checkpoint; not an approved library.\n' if incomplete else 'Artifact-complete Study package. This is not an approval decision.\n')
 with zipfile.ZipFile(output) as z:
  if z.testzip() is not None:raise ValueError('ZIP integrity failed')
 return {'path':str(output),'incomplete_checkpoint':incomplete,'static_result':report['static_result'],'approval_granted':False}
def main():
 p=argparse.ArgumentParser();p.add_argument('--study-root',required=True);p.add_argument('--output',required=True);p.add_argument('--stage',choices=['identification','structure','docx','metadata','qa']);p.add_argument('--allow-errors',action='store_true');a=p.parse_args()
 try:result=package(a.study_root,a.output,a.stage,a.allow_errors)
 except Exception as e:print(json.dumps({'error':str(e)}));return 1
 print(json.dumps(result,ensure_ascii=False,indent=2));return 0
if __name__=='__main__':sys.exit(main())
