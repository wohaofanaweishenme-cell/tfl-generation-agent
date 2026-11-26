"""Rule-based Shell Spec builder: content-list entry + study settings (+ reviewer answers) + template library -> Shell Spec.

This is the deterministic baseline the Agent will later wrap. It does three things:
  1. match()  - rank compatible templates/presets for an entry from Template_Index and explain the
                choice; flags ambiguity or 'no compatible template'.
  2. Builder  - fill the template skeleton and preset into a Shell Spec. Every element is a Slot tagged
                with its source (content_list / study_setting / template_default / unresolved).
                Missing study facts are never invented: they become unresolved slots with a question.
  3. validate against schemas/Shell_Spec.schema.json.

Token syntax inside template/preset text:
  {settings:dotted.path}  value from confirmed study settings (missing -> unresolved + question)
  {entry:field}           value from the content-list entry
  {level_names} {sort_rule} {sort_keys}  values computed while building

Reviewer answers (see apply_answers) are merged into the study settings before building, so a
regenerated shell picks them up with source=study_setting; question IDs come from a persistent
registry keyed by (output_id, element_path) so they stay stable across regenerations.
"""
import copy
import os
import re

from tfl_lib import ROOT, STYLE, load, norm, schema_errors, sha256

TOKEN = re.compile(r"\{(settings|entry):([A-Za-z0-9_.]+)\}|\{(level_names|sort_rule|sort_keys)\}")
BASELINE_WORDS = ("baseline", "screening", "pre-dose", "predose")


# ----------------------------------------------------------------------------- matching
def _has_term(ntitle, term):
    t = norm(term)
    return bool(t) and re.search(r"(^| )" + re.escape(t) + r"( |$)", ntitle) is not None


def core_title(entry):
    """Title without the population qualifier, table-number prefix and study-part suffix.

    Population names ('Safety Analysis Set', 'FAS', ...) describe who is analysed, not what is shown,
    so they must not drive template selection (same rule as stage 1, conventions 2.2)."""
    t = entry.get("original_title") or ""
    pop = entry.get("population") or ""
    if pop:
        t = re.sub(re.escape(pop), " ", t, flags=re.I)
    t = re.sub(r"^table [\d.\-]+\s*-\s*", "", t, flags=re.I)
    t = re.sub(r"\([^)]*(set|population|subjects|patients enrolled)[^)]*\)", " ", t, flags=re.I)
    t = re.sub(r"[\u2013-]\s*(dose escalation|dose expansion|expansion|part \d)\b.*$", " ", t, flags=re.I)
    t = re.sub(r"[\u2013-]\s*(safety analysis set|fas|randomized subjects|all subjects|immunogenicity analysis set|[a-z ]*analysis set)\s*$", " ", t, flags=re.I)
    t = re.sub(r"\b(safety|full|intent-to-treat|pharmacodynamic|efficacy evaluable|immunogenicity) analysis set\b", " ", t, flags=re.I)
    return t


def match(entry, index):
    """Return (selected_template_id or None, selected_preset_id or None, candidates, explanation)."""
    ntitle = norm(core_title(entry))
    same_type = [t for t in index["templates"] if t["output_type"] == entry.get("output_type")]
    cands = []
    for t in same_type:
        hits, neg = [], []
        score = 1 if len(same_type) == 1 else 0
        for term in t["match_cues"].get("title_terms", []):
            if norm(term) and norm(term) in ntitle:
                score += 3
                hits.append(term)
        for term in t["keywords"] + t["aliases"]:
            if _has_term(ntitle, term):
                score += 2
                hits.append(term)
        for term in t["match_cues"].get("negative_terms", []):
            if norm(term) and norm(term) in ntitle:
                score -= 4
                neg.append(term)
        best_preset, best_p = None, 0
        for p in t["presets"]:
            ps = sum(2 for k in p["keywords"] + p["aliases"] if _has_term(ntitle, k))
            if ps > best_p:
                best_preset, best_p = p["preset_id"], ps
        cands.append({"template_id": t["template_id"], "score": score + best_p, "matched_terms": sorted(set(hits)),
                      "negative_terms": neg, "preset_id": best_preset, "preset_score": best_p})
    cands.sort(key=lambda c: -c["score"])
    viable = [c for c in cands if c["score"] > 0]
    if not viable:
        return None, None, cands, "No template of type '%s' matches the title terms; no compatible template in the library." % entry.get("output_type")
    top = viable[0]
    if len(viable) > 1 and top["score"] - viable[1]["score"] < 2:
        return None, None, cands, "Ambiguous: %s (%d) vs %s (%d); human choice required." % (
            top["template_id"], top["score"], viable[1]["template_id"], viable[1]["score"])
    expl = "Selected %s (score %d): title terms %s" % (top["template_id"], top["score"], ", ".join(top["matched_terms"]) or "-")
    if top["negative_terms"]:
        expl += "; counter-indications %s" % ", ".join(top["negative_terms"])
    expl += "; preset %s." % (top["preset_id"] or "none matched")
    return top["template_id"], top["preset_id"], cands, expl


# ----------------------------------------------------------------------------- answers
def apply_answers(settings, answers):
    """Merge reviewer answers that name a settings path into a copy of the settings.

    answers: list of {"setting_path": "definitions.x" | "coding.meddra_version" | "visits" ..., "value": ...,
                      "question_ref": "<output_id>:<question_id>", "answered_by": str, "date": str}
    Returns (settings_copy, applied list)."""
    s = copy.deepcopy(settings)
    applied = []
    for a in answers or []:
        path = a.get("setting_path")
        if not path:
            continue
        cur = s
        parts = path.split(".")
        for part in parts[:-1]:
            cur = cur.setdefault(part, {})
        cur[parts[-1]] = a["value"]
        applied.append(path)
    if applied:
        s["version"] = "%s+answers(%d)" % (settings.get("version"), len(applied))
    return s, applied


# ----------------------------------------------------------------------------- building
class Builder:
    def __init__(self, entry, settings, template, template_path, preset, preset_path, style, registry=None):
        self.entry, self.settings, self.t, self.p, self.style = entry, settings, template, preset, style
        self.template_path, self.preset_path = template_path, preset_path
        self.issues = []
        self.computed = {}
        self.registry = registry if registry is not None else {}
        self.pstatus = (preset or {}).get("default_status", "needs_review")
        # endpoint-specific comparison settings, e.g. comparisons.time_to_event
        self.comp_path = ((template.get("config_options") or {}).get("comparison") or {}).get("setting_path")

    # -- questions (stable IDs per output_id + element_path)
    def question(self, path, kind, text):
        key = "%s|%s" % (self.entry["original_tfl_number"] + ":" + self.t["output_type"], path)
        qid = self.registry.get(key)
        if not qid:
            used = {v for v in self.registry.values()}
            n = 1
            while "Q%03d" % n in used:
                n += 1
            qid = "Q%03d" % n
            self.registry[key] = qid
        if not any(i["question_id"] == qid for i in self.issues):
            self.issues.append({"question_id": qid, "element_path": path, "kind": kind, "question": text, "answer": None})
        return qid

    def setting(self, dotted):
        cur = self.settings
        for part in dotted.split("."):
            if not isinstance(cur, dict) or part not in cur or cur[part] in (None, "", []):
                return None
            cur = cur[part]
        return cur

    @staticmethod
    def slot(value, source, status, **extra):
        s = {"value": value, "source": source, "status": status}
        s.update({k: v for k, v in extra.items() if v is not None})
        return s

    def resolve(self, raw):
        """Return (text, missing_keys, used_settings)."""
        missing, used = [], [False]

        def rep(m):
            kind, key, comp = m.group(1), m.group(2), m.group(3)
            if comp:
                return self.computed.get(comp, "")
            if kind == "entry":
                return str(self.entry.get(key) or "")
            if self.comp_path and key.startswith("comparisons.") and not key.startswith(self.comp_path + "."):
                key = self.comp_path + key[len("comparisons"):]
            val = self.setting(key)
            if val is None:
                missing.append(key)
                return "[" + key.split(".")[-1].replace("_", " ") + "]"
            used[0] = True
            return str(val)

        return TOKEN.sub(rep, raw), missing, used[0]

    def text_slot(self, raw, path, default_status):
        if raw is None:
            return self.slot(None, "template_default", default_status)
        value, missing, used = self.resolve(str(raw))
        if missing:
            qid = self.question(path, "missing", "Please confirm study setting(s): %s (needed for: %s)." % (", ".join(missing), value))
            return self.slot(value, "unresolved", "unresolved", question_id=qid, note="missing study setting: " + ", ".join(missing))
        if used:
            return self.slot(value, "study_setting", "resolved")
        return self.slot(value, "template_default", default_status)

    def list_slot(self, values, status, note=None, source="template_default"):
        return self.slot(list(values), source, status, note=note)

    def settings_list(self, key, path, placeholder, what):
        val = self.setting(key)
        if val:
            return self.slot(list(val), "study_setting", "resolved")
        qid = self.question(path, "missing", "Please confirm %s (study setting '%s')." % (what, key))
        return self.slot(list(placeholder), "unresolved", "unresolved", question_id=qid, note="placeholder until '%s' is confirmed" % key)

    # -- config
    def decide_config(self):
        ntitle = norm(self.entry.get("original_title"))
        cfg, notes = {}, []
        for name, opt in self.t["config_options"].items():
            chosen, why = opt["default"], "template default"
            for val, terms in (opt.get("cues") or {}).items():
                if any(norm(term) in ntitle for term in terms):
                    if isinstance(opt["default"], bool):
                        chosen = val == "true"
                    elif isinstance(opt["default"], int):
                        chosen = int(val)
                    else:
                        chosen = val
                    why = "content-list title cue"
                    break
            cfg[name] = chosen
            notes.append("%s=%s (%s)" % (name, chosen, why))
        if "column_layout" in cfg and len(self.settings.get("groups", [])) == 1 and not (self.settings.get("total_column") or {}).get("enabled"):
            cfg["column_layout"] = "single_all_subjects"
        if "comparison" in cfg:
            comp = self.setting(self.comp_path) or {}
            opts = self.t["config_options"]["comparison"]["values"]
            if "none" in opts:
                cfg["comparison"] = "columns" if comp.get("enabled") else "none"
                notes.append("comparison=%s (study setting %s.enabled=%s)" % (cfg["comparison"], self.comp_path, comp.get("enabled")))
        return cfg, notes

    # -- pieces
    def build_columns(self, cfg, pdef):
        groups = []
        for g in self.settings.get("groups", []):
            groups.append({"id": g["id"], "label": self.slot(g["label"], "study_setting", "resolved"), "show_n": g.get("show_n", True)})
        if not groups:
            qid = self.question("columns.groups", "missing", "Which treatment groups / cohorts are displayed?")
            groups = [{"id": "G1", "label": self.slot("[Group 1]", "unresolved", "unresolved", question_id=qid), "show_n": True}]
        tc = self.settings.get("total_column")
        if tc is None:
            qid = self.question("columns.total", "missing", "Should a Total column be displayed, and which groups does it pool?")
            total = {"enabled": self.slot(None, "unresolved", "unresolved", question_id=qid)}
        else:
            total = {"enabled": self.slot(bool(tc["enabled"]), "study_setting", "resolved")}
            if tc["enabled"]:
                total["label"] = self.slot(tc.get("label", "Total"), "study_setting", "resolved")
                total["member_group_ids"] = tc.get("member_group_ids", [g["id"] for g in groups])
        if self.t["skeleton"].get("columns", {}).get("suppress_total") and tc and tc.get("enabled"):
            total = {"enabled": self.slot(False, "template_default", "needs_review", note="Total column suppressed: between-group comparison table")}
        cols = {"groups": groups, "total": total}
        pc = pdef.get("columns", {})
        if pc.get("statistic_columns"):
            cols["statistic_columns"] = self.list_slot(pc["statistic_columns"], "resolved")
        if pc.get("category_columns"):
            cols["category_columns"] = self.list_slot(pc["category_columns"], self.pstatus)
        if cfg.get("comparison") in ("columns", "rows"):
            comp = self.setting(self.comp_path) or {}
            labels = [x for x in (comp.get("estimate_label"), comp.get("test_label")) if x]
            if comp.get("estimate_label"):
                cols["comparison_columns"] = self.list_slot(labels, "resolved", source="study_setting")
            else:
                qid = self.question("columns.comparison_columns", "missing", "Which between-group estimate (with CI level) is shown? (study setting '%s.estimate_label')" % self.comp_path)
                cols["comparison_columns"] = self.slot(["[Estimate (CI)]", comp.get("test_label") or "[p-value]"], "unresolved", "unresolved", question_id=qid,
                                                       note="missing study setting: %s.estimate_label" % self.comp_path)
        return cols

    def build_block(self, b, cfg):
        bt = b["block_type"]
        bid = b["block_id"]
        ps = self.pstatus
        out = {"block_id": bid, "block_type": bt, "label": self.text_slot(b.get("label", ""), "row_blocks[%s].label" % bid, ps)}
        if b.get("note"):
            out["label"]["note"] = b["note"]
        if "unit" in b:
            out["unit"] = self.text_slot(b["unit"], "row_blocks[%s].unit" % bid, ps)
        if bt == "continuous":
            out["statistics"] = self.list_slot(b.get("statistics", ["n", "mean_sd", "median", "min_max"]), "resolved")
        if bt == "categorical":
            out["statistics"] = self.list_slot(["n_pct"], "resolved")
            out["categories"] = self.list_slot(b.get("categories", []), ps)
            out["missing_row"] = self.slot(cfg.get("missing_display", "omit") != "omit", "template_default", "needs_review")
            if "multiple_response" in b:
                out["multiple_response"] = self.slot(b["multiple_response"], "template_default", "needs_review", note=b.get("note"))
        if bt == "coded_hierarchy":
            levels = list(b["levels"])
            if cfg.get("hierarchy_depth") == 1:
                levels = levels[-1:]
            self.computed["level_names"] = " and ".join(levels)
            self.computed["sort_rule"] = b.get("sort_rule", "")
            out["levels"] = self.list_slot(levels, ps, note=b.get("note"))
            out["dictionary"] = self.text_slot(b.get("dictionary"), "row_blocks[%s].dictionary" % bid, ps)
            out["sort_rule"] = self.slot(b.get("sort_rule"), "template_default", "needs_review")
            split = cfg.get("category_split", "none")
            out["category_split"] = self.slot(split, "content_list" if split != "none" else "template_default", "needs_review" if split != "none" else "resolved")
            if split != "none":
                out["split_categories"] = self.list_slot(b.get("split_categories", []), "needs_review")
        if bt in ("criterion", "endpoint"):
            items, missing = [], []
            for it in b["items"]:
                if it.get("where") == "comparison" and cfg.get("comparison", "columns") == "none":
                    continue
                label, miss, _ = self.resolve(it["label"])
                missing += miss
                items.append({**it, "label": label})
            if missing:
                qid = self.question("row_blocks[%s].items" % bid, "missing", "Please confirm study setting(s): %s (used in row labels)." % ", ".join(sorted(set(missing))))
                out["items"] = self.slot(items, "unresolved", "unresolved", question_id=qid)
            else:
                out["items"] = self.slot(items, "template_default", ps)
        if bt == "parameter_visit":
            out["cell_type"] = self.slot(b["cell_type"], "template_default", "resolved")
            out["parameters"] = self.list_slot(b.get("parameters", []), ps)
            out["visits"] = self.settings_list("visits", "row_blocks[%s].visits" % bid, ["Baseline", "[Visit 1]", "[Visit 2]"], "the visits / timepoints shown")
            if b["cell_type"] == "continuous":
                out["statistics"] = self.list_slot(b.get("statistics", ["n", "mean_sd", "median", "min_max"]), "resolved")
                out["change_from_baseline"] = self.slot(bool(cfg.get("change_from_baseline", True)), "template_default", "needs_review")
            else:
                out["categories"] = self.list_slot(b.get("categories", []), ps)
        if bt == "timepoint_stats":
            out["parameters"] = self.list_slot(b.get("parameters", []), ps)
            out["timepoints"] = self.settings_list("timepoints", "row_blocks[%s].timepoints" % bid, ["[Timepoint 1]", "[Timepoint 2]", "[Timepoint 3]"], "the nominal timepoints shown")
        if bt == "crosstab":
            for k in ("row_variable", "column_variable"):
                out[k] = self.text_slot(b.get(k), "row_blocks[%s].%s" % (bid, k), ps)
            out["row_categories"] = self.list_slot(b.get("row_categories", []), ps)
            out["parameters"] = self.list_slot(b.get("parameters", []), ps)
            if cfg.get("layout") == "long_transitions" or self.setting("visits"):
                out["visits"] = self.settings_list("visits", "row_blocks[%s].visits" % bid, ["[Post-baseline visit 1]", "[Post-baseline visit 2]"], "the post-baseline visits shown")
        if b.get("footnote_refs"):
            out["footnote_refs"] = list(b["footnote_refs"])
        return out

    def build_notes(self, pdef, cfg, blocks):
        t = self.t
        referenced = {r for b in blocks for r in b.get("footnote_refs", [])}
        raw = []
        for fn in pdef.get("footnotes", []) + t["skeleton"].get("footnotes", []):
            cond = fn.get("only_if_config")
            if cond and not all(cfg.get(k) in v for k, v in cond.items()):
                continue
            if fn.get("marker") and fn["id"] not in referenced:
                continue
            if any(r["id"] == fn["id"] for r in raw):
                continue
            raw.append(fn)
        order = []
        for b in blocks:
            for r in b.get("footnote_refs", []):
                if r not in order:
                    order.append(r)
        marked = sorted([fn for fn in raw if fn.get("marker")], key=lambda fn: order.index(fn["id"]) if fn["id"] in order else 99)
        general = [fn for fn in raw if not fn.get("marker")]
        letters = "abcdefghijklmnopqrstuvwxyz"
        notes = [{"id": fn["id"], "marker": letters[i], "text": self.text_slot(fn["text"], "footnotes[%s]" % fn["id"], self.pstatus)} for i, fn in enumerate(marked)]
        # skeleton notes of an approved template are approved display conventions -> resolved;
        # preset notes stay at the preset status (study-dependent candidate content)
        conv = "resolved" if t.get("review_status") == "approved" else "needs_review"
        skel_fn = {fn["id"] for fn in t["skeleton"].get("footnotes", [])}
        skel_pn = {pn["id"] for pn in t["skeleton"].get("programming_notes", [])}
        notes += [{"id": fn["id"], "marker": None, "text": self.text_slot(fn["text"], "footnotes[%s]" % fn["id"], conv if fn["id"] in skel_fn else self.pstatus)} for fn in general]
        pnotes = [{"id": pn["id"], "marker": None, "text": self.text_slot(pn["text"], "programming_notes[%s]" % pn["id"], conv if pn["id"] in skel_pn else self.pstatus)}
                  for pn in pdef.get("programming_notes", []) + t["skeleton"].get("programming_notes", [])]
        return notes, pnotes

    def build_figure(self, pdef, cfg, groups):
        sk = copy.deepcopy(self.t["skeleton"]["figure"])
        pf = copy.deepcopy(pdef.get("figure", {}))
        for axis in ("x_axis", "y_axis"):
            sk[axis].update(pf.pop(axis, {}))
        sk.update(pf)
        fig = {"plot_type": sk["plot_type"]}
        for axis in ("x_axis", "y_axis"):
            fig[axis] = {k: self.text_slot(v, "figure.%s.%s" % (axis, k), self.pstatus if k == "label" else "resolved") for k, v in sk[axis].items()}
        have_groups = bool(self.settings.get("groups"))
        fig["legend"] = self.slot(["%s (N=xx)" % g["label"]["value"] for g in groups], "study_setting" if have_groups else "unresolved",
                                  "resolved" if have_groups else "unresolved", question_id=None if have_groups else groups[0]["label"].get("question_id"))
        if cfg.get("scale_panels") == "linear_and_semilog" and "panels" not in sk:
            panels, src = ["Linear scale", "Semi-logarithmic scale"], "content_list"
        elif cfg.get("panel_by_group"):
            panels, src = [g["label"]["value"] for g in groups], "study_setting"
        else:
            panels, src = sk.get("panels", ["single panel"]), "template_default"
        fig["panels"] = self.slot(list(panels), src, "resolved" if src != "template_default" or panels == ["single panel"] else "needs_review")
        for k in ("reference_lines", "annotations"):
            if sk.get(k):
                fig[k] = self.list_slot(sk[k], "needs_review")
        if fig["plot_type"] == "KM":
            fig["risk_table"] = self.slot(bool(cfg.get("risk_table", sk.get("risk_table", True))), "template_default", "needs_review")
            fig["censor_marks"] = self.slot(bool(sk.get("censor_marks", True)), "template_default", "needs_review")
        return fig

    def build_listing(self, pdef):
        L = pdef.get("listing")
        lay = self.style["listing_layout"]
        if not L:
            qid = self.question("listing.fields", "missing", "No topic preset matched the title; which fields should this listing show?")
            fields = [{"id": "Subject_ID", "label": self.slot("Subject ID", "template_default", "resolved"), "kinds": ["subject_id"]},
                      {"id": "Treatment_group", "label": self.slot("Treatment group", "template_default", "resolved"), "kinds": ["group"]},
                      {"id": "Field", "label": self.slot("[Field]", "unresolved", "unresolved", question_id=qid), "kinds": ["text"]}]
            L = {"record_grain": "subject_event", "sort_keys": ["Treatment group", "Subject ID"], "group_by": ["Treatment group"]}
        else:
            fields = [{"id": f["id"], "label": self.slot(f["label"], "template_default", self.pstatus), "kinds": f["kinds"]} for f in L["fields"]]
        self.computed["sort_keys"] = ", ".join(L.get("sort_keys", []))
        return {"record_grain": self.slot(L.get("record_grain"), "template_default", "needs_review"),
                "fields": fields,
                "sort_keys": self.list_slot(L.get("sort_keys", []), "needs_review"),
                "group_by": self.list_slot(L.get("group_by", []), "needs_review"),
                "repeat_identifiers": self.list_slot(["Subject ID", "Treatment group"], "resolved"),
                "max_fields_per_panel": lay["max_fields_per_panel"]}

    # -- main
    def build(self):
        t, p, st = self.t, self.p, self.style
        cfg, cfg_notes = self.decide_config()
        pdef = copy.deepcopy((p or {}).get("defaults", {}))

        title = self.slot(self.entry["original_title"], "content_list", "resolved")
        if self.entry.get("population"):
            pop = self.slot(self.entry["population"], "content_list", "resolved")
        else:
            qid = self.question("population", "missing", "The content-list entry does not state the analysis population. Which population applies?")
            pop = self.slot(None, "unresolved", "unresolved", question_id=qid)

        columns = self.build_columns(cfg, pdef)
        blocks = [self.build_block(b, cfg) for b in pdef.get("row_blocks", [])]
        if p is None and t["output_type"] == "table":
            qid = self.question("row_blocks", "missing", "No topic preset matched the title; which rows / variables should this output contain?")
            blocks.append({"block_id": "rows", "block_type": "criterion", "label": self.slot("[Row content]", "unresolved", "unresolved", question_id=qid),
                           "items": self.slot([{"label": "[Row 1]", "indent": 0, "kind": "n_pct"}, {"label": "[Row 2]", "indent": 0, "kind": "n_pct"}], "unresolved", "unresolved", question_id=qid)})
        listing = self.build_listing(pdef) if t["output_type"] == "listing" else None
        figure = self.build_figure(pdef, cfg, columns["groups"]) if t["output_type"] == "figure" else None

        stub_raw = pdef.get("stub_header") or t["skeleton"].get("columns", {}).get("stub_header", "")
        lv = next((b["levels"]["value"] for b in blocks if b["block_type"] == "coded_hierarchy"), None)
        if lv:
            stub_raw = stub_raw.replace("{level_names}", " / ".join(lv))
        columns = {"stub_header": self.slot(stub_raw, "template_default", "resolved"), **columns}
        notes, pnotes = self.build_notes(pdef, cfg, blocks)

        page_set = self.settings.get("page", {})
        page = {"orientation": page_set.get("orientation", st["page"]["orientation"]), "paper": page_set.get("paper", st["page"]["paper"]),
                "font": st["page"]["font"], "font_size_pt": st["page"]["font_size_pt"], "include_programming_notes": True}
        return {
            "schema_version": "3.0",
            "output_id": self.entry["original_tfl_number"],
            "output_type": t["output_type"],
            "template_id": t["template_id"],
            "template_version": t["version"],
            "preset_ids": [p["preset_id"]] if p else [],
            "title": title,
            "population": pop,
            "columns": columns,
            "row_blocks": blocks,
            "footnotes": notes,
            "programming_notes": pnotes,
            "figure": figure,
            "listing": listing,
            "config": cfg,
            "page": page,
            "issues": self.issues,
            "provenance": {
                "content_list_entry": {k: v for k, v in self.entry.items() if k != "source_regions"},
                "template_file_sha256": sha256(self.template_path),
                "preset_file_sha256": {p["preset_id"]: sha256(self.preset_path)} if p else {},
                "style_guide_version": st["version"],
                "study_settings_version": "%s@%s" % (self.settings.get("study_id"), self.settings.get("version")),
                "match": {},
                "generated_by": "tools/build_spec.py (rule-based); config: " + "; ".join(cfg_notes),
            },
        }


def build_for_entry(entry, settings, answers=None, registry=None, index=None):
    """Returns (spec or None, no-template record or None)."""
    index = index or load(os.path.join(ROOT, "Template_Index.json"))
    style = load(STYLE)
    settings, applied = apply_answers(settings, answers)
    tid, pid, cands, expl = match(entry, index)
    if tid is None:
        return None, {"output_id": entry["original_tfl_number"], "output_type": entry.get("output_type"), "status": "no_compatible_template" if not expl.startswith("Ambiguous") else "ambiguous_match",
                      "title": entry.get("original_title"), "explanation": expl, "candidates": cands}
    tinfo = next(t for t in index["templates"] if t["template_id"] == tid)
    tpath = os.path.join(ROOT, tinfo["path"])
    preset, ppath = None, None
    if pid:
        ppath = os.path.join(ROOT, next(p["path"] for p in tinfo["presets"] if p["preset_id"] == pid))
        preset = load(ppath)
    spec = Builder(entry, settings, load(tpath), tpath, preset, ppath, style, registry).build()
    spec["provenance"]["match"] = {"selected": tid, "candidates": cands, "explanation": expl}
    if applied:
        spec["provenance"]["generated_by"] += "; reviewer answers applied: " + ", ".join(applied)
    errs = schema_errors("Shell_Spec.schema.json", spec)
    if errs:
        raise SystemExit("Shell Spec schema errors for %s:\n  %s" % (entry["original_tfl_number"], "\n  ".join(errs[:20])))
    return spec, None
