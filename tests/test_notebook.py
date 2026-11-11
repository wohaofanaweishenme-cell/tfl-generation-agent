"""Execute the actual Jupyter interface against synthetic fixture data."""
from pathlib import Path
import nbformat
from nbclient import NotebookClient

ROOT=Path(__file__).resolve().parents[1]

def test_notebook_runs_end_to_end():
    nb=nbformat.read(ROOT/'notebooks'/'01_TFL_Generation_MVP.ipynb',as_version=4)
    client=NotebookClient(nb,timeout=120,kernel_name='python3',resources={'metadata':{'path':str(ROOT)}},allow_errors=False)
    client.execute()
    text='\n'.join(str(x.get('text','')) for cell in nb.cells if cell.cell_type=='code' for x in cell.get('outputs',[]))
    assert '"generated": 1' in text
    assert (ROOT/'output'/'notebook_demo'/'shells'/'Table_14.2.1.docx').exists()
