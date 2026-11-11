import json,subprocess,concurrent.futures,sys
from pathlib import Path
r=Path(__file__).resolve().parents[1];p=Path('/Users/xinxin/.codex/plugins/cache/openai-primary-runtime/documents/26.1105.12137/skills/documents/render_docx.py');py='/Users/xinxin/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3'
m=json.loads((r/'source_registry/Shell_Manifest.json').read_text());subset=set(sys.argv[1:])
def one(sh):
 tid=sh['template_id'];out=r/'qa/docx_renders'/tid;out.mkdir(parents=True,exist_ok=True)
 with (out/'render.log').open('w') as log:
  result=subprocess.run([py,str(p),str(r/'TFL_Template_Library'/sh['planned_file_path']),'--output_dir',str(out),'--emit_pdf'],stdout=log,stderr=subprocess.STDOUT)
 imgs=list(out.glob('page-*.png'));return dict(template_id=tid,returncode=result.returncode,pages=len(imgs),status='rendered' if result.returncode==0 and imgs else 'failed')
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
 results=list(pool.map(one,[sh for sh in m['shells'] if not subset or sh['template_id'] in subset]))
(r/'qa/DOCX_Render_Results.json').write_text(json.dumps(results,indent=2)+'\n');print(json.dumps(dict(files=len(results),pages=sum(x['pages'] for x in results),failures=[x for x in results if x['status']=='failed']),indent=2))
