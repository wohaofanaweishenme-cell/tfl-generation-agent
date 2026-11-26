"""Generic figure renderer: Shell Spec (output_type=figure) -> DOCX with an embedded labelled empty frame.

The plotting function is looked up from the template's figure_plot.plotter ("path.py:function"),
called with data=None, and the PNG is embedded; title, population, footnotes and programming notes
stay as editable Word text.
"""
import importlib.util
import os

from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches

from common import bookmark, new_document, notes_block, tight, title_block

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def load_plotter(spec_ref):
    path, func = spec_ref.split(":")
    full = os.path.join(ROOT, path)
    mod_spec = importlib.util.spec_from_file_location("plotter_" + func, full)
    mod = importlib.util.module_from_spec(mod_spec)
    mod_spec.loader.exec_module(mod)
    return getattr(mod, func)


def render(spec, style, template, out_path, png_path):
    plotter = load_plotter(template["figure_plot"]["plotter"])
    fig = plotter(spec, data=None, style=style)
    fig.savefig(png_path, dpi=200, facecolor="white")
    from PIL import Image
    Image.open(png_path).convert("RGB").save(png_path)  # no alpha channel: avoids grey backgrounds in some viewers
    doc, usable = new_document(spec, style)
    first = title_block(doc, spec, style)
    p = tight(doc.add_paragraph(), after=4)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(png_path, width=Inches(min(usable, style["figure_layout"]["width_in"])))
    last = notes_block(doc, spec, style) or p
    name = bookmark(first, last, spec["output_id"])
    doc.save(out_path)
    return name
