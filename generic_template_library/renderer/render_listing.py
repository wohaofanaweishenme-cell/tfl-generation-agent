"""Generic listing renderer: Shell Spec (output_type=listing) -> editable DOCX.

Fields become columns (stacked sub-fields share a cell, joined by ' / '). When there are more fields
than style.listing_layout.max_fields_per_panel, the listing is split into panels and the repeat
identifiers (subject ID, group) are repeated on every panel. Group display follows config.group_display.
Three placeholder rows per group show the cell formats; no data.
"""
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH

from common import add_run, add_slot, bookmark, fix_table_layout, new_document, no_table_borders, notes_block, set_cell_border, slot_text, tight, title_block


def _panels(fields, repeat_labels, max_fields):
    ids = [f for f in fields if slot_text(f["label"], {"unresolved_display": {"format": "{summary}"}})[0] in repeat_labels]
    rest = [f for f in fields if f not in ids]
    per = max(1, max_fields - len(ids))
    n = max(1, -(-len(rest) // per))
    size = -(-len(rest) // n) if rest else 0
    chunks = [rest[i:i + size] for i in range(0, len(rest), size)] if rest else [[]]
    return [ids + c for c in chunks]


def render(spec, style, out_path):
    doc, usable = new_document(spec, style)
    first = title_block(doc, spec, style)
    L = spec["listing"]
    lay = style["listing_layout"]
    cfg = spec.get("config", {})
    group_header = cfg.get("group_display", "header_rows") == "header_rows"
    fields = list(L["fields"])
    if group_header:
        fields = [f for f in fields if "group" not in f["kinds"]]
    repeat = list(L["repeat_identifiers"]["value"])
    panels = _panels(fields, repeat, L.get("max_fields_per_panel", lay["max_fields_per_panel"]))
    groups = [slot_text(g["label"], style)[0] for g in spec["columns"]["groups"]]
    shown_groups = groups[:2] if group_header else [None]

    for pi, pf in enumerate(panels):
        if len(panels) > 1:
            pp = tight(doc.add_paragraph(), before=4)
            add_run(pp, "Panel %d of %d" % (pi + 1, len(panels)), style, italic=True)
        nrows = 1 + len(shown_groups) * (lay["sample_rows"] + (1 if group_header else 0))
        table = doc.add_table(rows=nrows, cols=len(pf))
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        no_table_borders(table)
        for ci, f in enumerate(pf):
            p = tight(table.rows[0].cells[ci].paragraphs[0])
            add_slot(p, f["label"], style, bold=True)
            set_cell_border(table.rows[0].cells[ci], top="single", bottom="single")
        r = 1
        for g in shown_groups:
            if group_header:
                cell = table.rows[r].cells[0].merge(table.rows[r].cells[len(pf) - 1]) if len(pf) > 1 else table.rows[r].cells[0]
                add_run(tight(cell.paragraphs[0], before=2), "Treatment group: %s" % g, style, bold=True)
                r += 1
            for _ in range(lay["sample_rows"]):
                for ci, f in enumerate(pf):
                    text = " / ".join(lay["placeholders"].get(k, "[x]") for k in f["kinds"])
                    vp = tight(table.rows[r].cells[ci].paragraphs[0])
                    add_run(vp, text, style)
                r += 1
        for ci in range(len(pf)):
            set_cell_border(table.rows[-1].cells[ci], bottom="single")
        fix_table_layout(table, [usable / len(pf)] * len(pf), 1)
        tight(doc.add_paragraph())
    last = notes_block(doc, spec, style) or doc.paragraphs[-1]
    name = bookmark(first, last, spec["output_id"])
    doc.save(out_path)
    return name
