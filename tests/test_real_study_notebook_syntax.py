"""Static validation of the real-study demo cells (no Colab required)."""
import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_real_study_notebook_python_cells_parse():
    notebook = json.loads((ROOT / "notebooks" / "03_Real_Study_DeepSeek_Colab.ipynb").read_text())
    code = [cell["source"] for cell in notebook["cells"] if cell["cell_type"] == "code"]
    assert code
    for i, lines in enumerate(code):
        ast.parse("".join(lines), filename=f"demo_cell_{i}.py")
    all_code = "\n".join("".join(lines) for lines in code)
    assert "completion.get('attempted'" in all_code
    assert "best_candidate_template_id" in all_code
    assert "drive.mount" in all_code
    assert "files.upload()" not in all_code
