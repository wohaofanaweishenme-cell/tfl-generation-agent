"""Generic table renderer: Shell Spec (output_type=table) -> editable DOCX.

Driven only by the Shell Spec and the House Style Guide; there is no template-specific code.
Column modes (decided from the spec):
  groups      - treatment groups (+ Total), optional sub-columns per group, optional comparison columns
  statistics  - columns.statistic_columns; groups become row blocks (timepoint_stats)
  categories  - columns.category_columns; groups become row blocks (crosstab matrix)
Row generation is per block_type.
"""
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH

from common import add_run, add_slot, bookmark, fix_table_layout, new_document, no_table_borders, notes_block, set_cell_border, slot_text, tight, title_block

BASELINE_WORDS = ("baseline", "screening", "pre-dose", "predose")


def _vals(slot):
    return list((slot or {}).get("value") or [])


class Col:
    def __init__(self, header, sub=None, role="group", n_text=""):
        self.header, self.sub, self.role, self.n_text = header, sub, role, n_text


def _columns(spec, style):
    """Return (mode, [Col], spans[(header, n_text, span)])."""
    cfg = spec.get("config", {})
    c = spec["columns"]
    groups = [(g["label"], "(N=xx)" if g.get("show_n", True) else "") for g in c["groups"]]
    tot = c["total"]
    if tot["enabled"].get("value") is True:
        groups.append((tot.get("label"), "(N=xx)"))
    elif tot["enabled"].get("status") == "unresolved":
        groups.append(({"value": "Total", "source": "unresolved", "status": "unresolved", "question_id": tot["enabled"].get("question_id")}, "(N=xx)"))
    if c.get("statistic_columns"):
        fmt = style["statistic_formats"]
        cols = [Col(fmt[s]["label"], role=s) for s in _vals(c["statistic_columns"])]
        return "statistics", cols, [(None, "", len(cols))]
    blocks = spec["row_blocks"]
    if c.get("category_columns") and cfg.get("layout") != "long_transitions":
        cols = [Col(cat, role="n_pct") for cat in _vals(c["category_columns"])]
        xt = next((b for b in blocks if b["block_type"] == "crosstab"), None)
        head = xt.get("column_variable") if xt else None
        return "categories", cols, [(head, "", len(cols))]
    subs = [None]
    coded = next((b for b in blocks if b["block_type"] == "coded_hierarchy"), None)
    if coded and cfg.get("category_split") == "subcolumns" and coded.get("split_categories"):
        subs = _vals(coded["split_categories"])
    if cfg.get("event_counts"):
        subs = [x for s in subs for x in ((s or "n (%)"), "E")]
    cols, spans = [], []
    for label, ntext in groups:
        for s in subs:
            cols.append(Col(label, sub=s, role="group", n_text=ntext))
        spans.append((label, ntext, len(subs)))
    if cfg.get("comparison") == "columns" and c.get("comparison_columns"):
        comp = c["comparison_columns"]
        unresolved = comp.get("status") == "unresolved"
        for lab in _vals(comp):
            hdr = {"value": lab, "source": comp["source"], "status": comp["status"], "question_id": comp.get("question_id")} if unresolved else lab
            cols.append(Col(hdr, role="comparison"))
            spans.append((hdr, "", 1))
    return "groups", cols, spans


def _ph(kind, col, style):
    fmt = style["statistic_formats"]
    if col.sub == "E":
        return "xx"
    if kind in fmt:
        return fmt[kind]["placeholder"]
    return fmt["n_pct"]["placeholder"]


def _marked(slot, value):
    """Show the unresolved marker on one row of a placeholder list."""
    return dict(slot, value=value)


def _rows(spec, style, mode):
    """Yield (label, indent, kind, where, suffix, unit_slot). kind None -> label-only row."""
    cfg = spec.get("config", {})
    fmt = style["statistic_formats"]
    fnmark = {fn["id"]: fn["marker"] for fn in spec["footnotes"] if fn.get("marker")}
    group_labels = [slot_text(g["label"], style)[0] for g in spec["columns"]["groups"]]
    if spec["columns"]["total"]["enabled"].get("value") is True:
        group_labels.append(slot_text(spec["columns"]["total"].get("label"), style)[0])
    for b in spec["row_blocks"]:
        bt = b["block_type"]
        refs = "".join(" [%s]" % fnmark[r] for r in b.get("footnote_refs", []) if r in fnmark)
        if bt == "continuous":
            unit, _ = slot_text(b.get("unit"), style)
            yield (b["label"], 0, None, "groups", (" (%s)" % unit if unit else "") + refs, b.get("unit"))
            for s in _vals(b["statistics"]):
                yield (fmt[s]["label"], 1, s, "groups", "", None)
        elif bt == "categorical":
            yield (b["label"], 0, None, "groups", ", n (%)" + refs, None)
            for c in _vals(b["categories"]):
                yield (c, 1, "n_pct", "groups", "", None)
            if b.get("missing_row", {}).get("value"):
                yield ("Missing", 1, "n", "groups", "", None)
        elif bt == "any_row":
            yield (b["label"], 0, "n_pct", "groups", refs, None)
        elif bt == "coded_hierarchy":
            levels = _vals(b["levels"])
            cats = _vals(b.get("split_categories")) if cfg.get("category_split") == "subrows" else []

            def term(text, indent):
                yield (text, indent, "n_pct", "groups", "", None)
                for c in cats:
                    yield (c, indent + 1, "n_pct", "groups", "", None)

            if len(levels) >= 2:
                for i in (1, 2):
                    yield from term("[%s %d]" % (levels[0], i), 0)
                    for j in (1, 2):
                        yield from term("[%s %d]" % (levels[1], j), 1)
                    yield ("...", 1, None, "groups", "", None)
            else:
                for j in (1, 2, 3):
                    yield from term("[%s %d]" % (levels[0], j), 0)
                yield ("...", 0, None, "groups", "", None)
        elif bt in ("criterion", "endpoint"):
            items = b["items"]
            unresolved = items.get("status") == "unresolved"
            for it in _vals(items):
                where = it.get("where", "groups")
                if where == "comparison" and cfg.get("comparison") == "rows":
                    where = "first_group"
                label = _marked(items, it["label"]) if (unresolved and "[" in it["label"]) else it["label"]
                yield (label, it["indent"], None if it["kind"] == "header" else it["kind"], where, "", None)
        elif bt == "parameter_visit":
            visits = b["visits"]
            cont = b["cell_type"]["value"] == "continuous"
            cfb = b.get("change_from_baseline", {}).get("value")
            for prm in _vals(b["parameters"]):
                yield (prm, 0, None, "groups", "", None)
                for vi, v in enumerate(_vals(visits)):
                    vlabel = _marked(visits, v) if visits.get("status") == "unresolved" and vi == 0 else v
                    yield (vlabel, 1, None, "groups", "", None)
                    if cont:
                        for s in _vals(b["statistics"]):
                            yield (fmt[s]["label"], 2, s, "groups", "", None)
                        if cfb and not any(w in v.lower() for w in BASELINE_WORDS):
                            yield ("Change from baseline", 2, None, "groups", "", None)
                            for s in _vals(b["statistics"]):
                                yield (fmt[s]["label"], 3, s, "groups", "", None)
                    else:
                        yield ("n", 2, "n", "groups", "", None)
                        for c in _vals(b["categories"]):
                            yield (c, 2, "n_pct", "groups", "", None)
                yield ("...", 1, None, "groups", "", None)
        elif bt == "timepoint_stats":
            tps = b["timepoints"]
            for gl in group_labels:
                yield (gl + " (N=xx)", 0, None, "all", "", None)
                for prm in _vals(b["parameters"]):
                    yield (prm, 1, None, "all", "", None)
                    for ti, tp in enumerate(_vals(tps)):
                        tl = _marked(tps, tp) if tps.get("status") == "unresolved" and ti == 0 else tp
                        yield (tl, 2, "stat", "all", "", None)
        elif bt == "crosstab":
            cats = _vals(b["row_categories"])
            vslot = b.get("visits")
            visits = _vals(vslot) or [None]
            if mode == "categories":
                for gl in group_labels:
                    yield (gl + " (N=xx)", 0, None, "all", "", None)
                    for prm in _vals(b["parameters"]):
                        yield (prm, 1, None, "all", "", None)
                        for vi, v in enumerate(visits):
                            ind = 2
                            if v:
                                yield (_marked(vslot, v) if vslot.get("status") == "unresolved" and vi == 0 else v, 2, None, "all", "", None)
                                ind = 3
                            yield (b["row_variable"], ind, None, "all", "", None)
                            for c in cats:
                                yield (c, ind + 1, "n_pct", "all", "", None)
            else:
                base = [c for c in cats if c.lower() not in ("total", "missing")]
                for prm in _vals(b["parameters"]):
                    yield (prm, 0, None, "groups", "", None)
                    for vi, v in enumerate(visits):
                        if v:
                            yield (_marked(vslot, v) if vslot.get("status") == "unresolved" and vi == 0 else v, 1, None, "groups", "", None)
                        yield ("n", 2, "n", "groups", "", None)
                        for c in base:
                            yield (c, 2, "n_pct", "groups", "", None)
                        yield ("Shift from baseline", 2, None, "groups", "", None)
                        for a in base:
                            for c in base:
                                yield ("%s -> %s" % (a, c), 3, "n_pct", "groups", "", None)
        else:
            yield (b["label"], 0, None, "groups", refs, None)


def render(spec, style, out_path):
    doc, usable = new_document(spec, style)
    first = title_block(doc, spec, style)
    mode, cols, spans = _columns(spec, style)
    two_rows = any(c.sub for c in cols) or (mode != "groups" and spans[0][0] is not None)
    ncols = 1 + len(cols)
    rows = list(_rows(spec, style, mode))
    nhead = 2 if two_rows else 1
    table = doc.add_table(rows=nhead + len(rows), cols=ncols)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    no_table_borders(table)
    stub_w = min(3.6, usable * (0.30 if ncols > 6 else 0.38))
    other_w = (usable - stub_w) / max(1, ncols - 1)
    widths = [stub_w] + [other_w] * (ncols - 1)

    # header
    add_slot(tight(table.rows[0].cells[0].paragraphs[0]), spec["columns"]["stub_header"], style, bold=True)
    if mode == "groups":
        c0 = 1
        for label, ntext, span in spans:
            cell = table.rows[0].cells[c0]
            if span > 1:
                cell = cell.merge(table.rows[0].cells[c0 + span - 1])
            p = tight(cell.paragraphs[0])
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            if isinstance(label, dict):
                add_slot(p, label, style, bold=True)
            else:
                add_run(p, label or "", style, bold=True)
            if ntext:
                add_run(p, "\n" + ntext, style, bold=True)
            if two_rows:
                for k in range(span):
                    sub = cols[c0 - 1 + k].sub
                    if sub:
                        sp = tight(table.rows[1].cells[c0 + k].paragraphs[0])
                        sp.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        add_run(sp, sub, style, bold=True)
                if span == 1 and not cols[c0 - 1].sub:
                    table.rows[0].cells[c0].merge(table.rows[1].cells[c0])
            c0 += span
    else:
        hdr_row = 1 if two_rows else 0
        if two_rows:
            cell = table.rows[0].cells[1].merge(table.rows[0].cells[ncols - 1])
            p = tight(cell.paragraphs[0])
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            add_slot(p, spans[0][0], style, bold=True)
        for k, col in enumerate(cols):
            p = tight(table.rows[hdr_row].cells[1 + k].paragraphs[0])
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            add_run(p, col.header, style, bold=True)
    if two_rows:
        table.rows[0].cells[0].merge(table.rows[1].cells[0])
    for ci in range(ncols):
        set_cell_border(table.rows[0].cells[ci], top="single")
        set_cell_border(table.rows[nhead - 1].cells[ci], bottom="single")

    # body
    indent = " " * style["table_layout"]["indent_per_level_spaces"]
    first_group_idx = next((i for i, c in enumerate(cols) if c.role == "group"), 0)
    for ri, (label, level, kind, where, suffix, unit) in enumerate(rows):
        row = table.rows[nhead + ri]
        p = tight(row.cells[0].paragraphs[0])
        if isinstance(label, dict) and unit and slot_text(unit, style)[1]:
            add_slot(p, label, style, prefix=indent * level, suffix=" (")
            add_slot(p, unit, style, suffix=")" + suffix.split(")", 1)[-1])
        elif isinstance(label, dict):
            add_slot(p, label, style, prefix=indent * level, suffix=suffix)
        else:
            add_run(p, indent * level + str(label) + suffix, style)
        if not kind:
            continue
        for ci, col in enumerate(cols):
            if mode == "statistics":
                text = _ph(col.role, col, style)
            elif mode == "categories":
                text = _ph(kind, col, style)
            elif col.role == "comparison":
                if where not in ("comparison", "both"):
                    continue
                is_p = "p-value" in str(slot_text(col.header, style)[0] if isinstance(col.header, dict) else col.header).lower()
                if is_p != (kind == "p_value"):
                    continue
                text = _ph(kind, col, style)
            else:
                if where == "comparison" or (where == "first_group" and ci != first_group_idx):
                    continue
                text = _ph(kind, col, style)
            vp = tight(row.cells[1 + ci].paragraphs[0])
            vp.alignment = WD_ALIGN_PARAGRAPH.CENTER
            add_run(vp, text, style)
    for ci in range(ncols):
        set_cell_border(table.rows[-1].cells[ci], bottom="single")
    fix_table_layout(table, widths, nhead)

    tight(doc.add_paragraph())
    last = notes_block(doc, spec, style) or doc.paragraphs[-1]
    name = bookmark(first, last, spec["output_id"])
    doc.save(out_path)
    return name
