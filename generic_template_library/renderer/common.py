"""Shared python-docx helpers: page setup, header/footer, slot text with unresolved highlighting,
title block, notes, borders and the per-output bookmark (House Style Guide v1.0)."""
import re

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_COLOR_INDEX, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

PAPER = {"letter": (8.5, 11.0), "a4": (8.27, 11.69)}


def slot_text(slot, style):
    """Return (text, unresolved?) for a Slot. Unresolved slots use the style-guide marker."""
    if slot is None:
        return "", False
    val = slot.get("value")
    if isinstance(val, list):
        val = ", ".join(val)
    if slot.get("status") in ("unresolved", "conflict"):
        summary = val if val else slot.get("note", "value required")
        marker = style["unresolved_display"]["format"].format(summary=summary, question_id=slot.get("question_id", "Q???"))
        return marker, True
    return ("" if val is None else str(val)), False


def add_run(par, text, style, bold=False, italic=False, color=None, highlight=False, size=None):
    run = par.add_run(text)
    run.font.name = style["page"]["font"]
    run._element.rPr.rFonts.set(qn("w:eastAsia"), style["page"]["font"])
    run.font.size = Pt(size or style["page"]["font_size_pt"])
    run.bold = bold
    run.italic = italic
    if color:
        run.font.color.rgb = RGBColor.from_string(color)
    if highlight:
        run.font.highlight_color = WD_COLOR_INDEX.YELLOW
    return run


def add_slot(par, slot, style, prefix="", suffix="", **kw):
    text, unresolved = slot_text(slot, style)
    if prefix:
        add_run(par, prefix, style, **kw)
    add_run(par, text, style, highlight=unresolved, **kw)
    if suffix:
        add_run(par, suffix, style, **kw)


def tight(par, before=0, after=0):
    pf = par.paragraph_format
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    pf.line_spacing = 1.0
    return par


def new_document(spec, style):
    doc = Document()
    normal = doc.styles["Normal"]
    normal.font.name = style["page"]["font"]
    normal.font.size = Pt(style["page"]["font_size_pt"])
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), style["page"]["font"])
    sec = doc.sections[0]
    w, h = PAPER[spec["page"]["paper"]]
    if spec["page"]["orientation"] == "landscape":
        sec.orientation = WD_ORIENT.LANDSCAPE
        w, h = h, w
    sec.page_width, sec.page_height = Inches(w), Inches(h)
    m = style["page"]["margins_in"]
    sec.top_margin, sec.bottom_margin = Inches(m["top"]), Inches(m["bottom"])
    sec.left_margin, sec.right_margin = Inches(m["left"]), Inches(m["right"])
    _header_footer(sec, style, w - m["left"] - m["right"])
    return doc, w - m["left"] - m["right"]


def _field(par, instr, style):
    for kind, text in (("begin", None), ("instr", instr), ("separate", None), ("text", "1"), ("end", None)):
        if kind == "instr":
            r = add_run(par, "", style)
            el = OxmlElement("w:instrText")
            el.set(qn("xml:space"), "preserve")
            el.text = text
            r._element.append(el)
        elif kind == "text":
            add_run(par, text, style)
        else:
            r = add_run(par, "", style)
            el = OxmlElement("w:fldChar")
            el.set(qn("w:fldCharType"), kind)
            r._element.append(el)


def _clear_default_tabs(par):
    for pos in (3.25, 6.5):  # tab stops inherited from the built-in Header/Footer styles
        par.paragraph_format.tab_stops.add_tab_stop(Inches(pos), alignment=WD_TAB_ALIGNMENT.CLEAR)


def _header_footer(sec, style, usable_in):
    pg = style["page"]
    hp = tight(sec.header.paragraphs[0])
    _clear_default_tabs(hp)
    hp.paragraph_format.tab_stops.add_tab_stop(Inches(usable_in), alignment=WD_TAB_ALIGNMENT.RIGHT)
    add_run(hp, pg["header_left"] + "\t", style)
    add_run(hp, "Page ", style)
    _field(hp, "PAGE", style)
    add_run(hp, " of ", style)
    _field(hp, "NUMPAGES", style)
    fp = tight(sec.footer.paragraphs[0])
    _clear_default_tabs(fp)
    fp.paragraph_format.tab_stops.add_tab_stop(Inches(usable_in), alignment=WD_TAB_ALIGNMENT.RIGHT)
    add_run(fp, pg["footer_left"] + "\t" + pg["footer_right"], style)


def title_block(doc, spec, style):
    label = {"table": "Table", "listing": "Listing", "figure": "Figure"}[spec["output_type"]]
    p1 = tight(doc.add_paragraph())
    p1.alignment = WD_ALIGN_PARAGRAPH.CENTER
    start = add_run(p1, "%s %s" % (label, spec["output_id"]), style, bold=True)
    p2 = tight(doc.add_paragraph())
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    add_slot(p2, spec["title"], style, bold=True)
    p3 = tight(doc.add_paragraph(), after=6)
    p3.alignment = WD_ALIGN_PARAGRAPH.CENTER
    add_slot(p3, spec["population"], style)
    return p1


def notes_block(doc, spec, style):
    last = None
    for fn in spec["footnotes"]:
        p = tight(doc.add_paragraph())
        add_slot(p, fn["text"], style, prefix=("[%s] " % fn["marker"]) if fn.get("marker") else "")
        last = p
    if spec["page"].get("include_programming_notes", True):
        pn_style = style["programming_notes"]
        for pn in spec["programming_notes"]:
            p = tight(doc.add_paragraph(), before=2 if last is None else 0)
            add_slot(p, pn["text"], style, prefix=pn_style["prefix"], italic=pn_style["style"]["italic"], color=pn_style["style"]["color_rgb"])
            last = p
    return last


def bookmark(start_par, end_par, output_id):
    name = ("OUT_" + re.sub(r"[^A-Za-z0-9]", "_", output_id))[:40]
    bs = OxmlElement("w:bookmarkStart")
    bs.set(qn("w:id"), "1")
    bs.set(qn("w:name"), name)
    be = OxmlElement("w:bookmarkEnd")
    be.set(qn("w:id"), "1")
    start_par._p.insert(0, bs)
    end_par._p.append(be)
    return name


def set_cell_border(cell, **edges):
    tcPr = cell._tc.get_or_add_tcPr()
    borders = tcPr.find(qn("w:tcBorders"))
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        tcPr.append(borders)
    for edge, val in edges.items():
        el = OxmlElement("w:" + edge)
        el.set(qn("w:val"), val)
        el.set(qn("w:sz"), "6")
        el.set(qn("w:color"), "000000")
        borders.append(el)


def no_table_borders(table):
    tblPr = table._tbl.tblPr
    b = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement("w:" + edge)
        el.set(qn("w:val"), "nil")
        b.append(el)
    tblPr.append(b)


def fix_table_layout(table, widths_in, header_rows):
    """Fixed column widths (honoured by Word and LibreOffice), tight paragraphs, repeated header rows."""
    table.autofit = False
    tblPr = table._tbl.tblPr
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    tblPr.append(layout)
    grid = table._tbl.tblGrid
    for gc, w in zip(grid.findall(qn("w:gridCol")), widths_in):
        gc.set(qn("w:w"), str(int(w * 1440)))
    for r_i, row in enumerate(table.rows):
        for c_i, cell in enumerate(row.cells):
            if c_i < len(widths_in):
                cell.width = Inches(widths_in[c_i])
            for par in cell.paragraphs:
                tight(par)
        trPr = row._tr.get_or_add_trPr()
        cant = OxmlElement("w:cantSplit")
        trPr.append(cant)
        if r_i < header_rows:
            hdr = OxmlElement("w:tblHeader")
            trPr.append(hdr)
