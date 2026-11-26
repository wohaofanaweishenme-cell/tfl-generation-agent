"""Read-only adapter for approved Generic TFL Library v1.x.

Do not route these records through the legacy source-DOCX loader.
The index is for discovery; approved JSON files are authoritative.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path


def _read(path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class GenericLibrary:
    """A validated snapshot. Loading never rewrites library artifacts."""

    def __init__(self, root):
        self.root = Path(root).resolve()
        self.index = _read(self.root / "Template_Index.json")
        self.keyword_index = _read(self.root / "Keyword_Index.json")
        approval = _read(self.root / "approvals/Approval_Record.json")["current"]
        items = approval["items"]
        self.approved = {x["path"]: x for x in items}
        if len(self.approved) != len(items):
            raise ValueError("Duplicate approval paths")
        for key in ("library", "style_guide_version", "style_guide_sha256"):
            if self.index[key] != self.keyword_index[key]:
                raise ValueError(f"Inconsistent indexes: {key}")
        self.templates = {}
        self.presets = {}
        self._definitions = {}
        self._preset_definitions = {}
        for t in self.index["templates"]:
            tid = t["template_id"]
            if tid in self.templates:
                raise ValueError(f"Duplicate template {tid}")
            if t["review_status"] != "approved":
                raise ValueError(f"Unapproved template in index: {tid}")
            d = self._approved_json(t["path"], t["sha256"])
            if d["template_id"] != tid or d["version"] != t["version"]:
                raise ValueError(f"Template identity mismatch: {tid}")
            for field in ("output_type", "name", "intended_use", "not_for",
                          "keywords", "aliases", "match_cues", "review_status"):
                if d[field] != t[field]:
                    raise ValueError(f"Stale template index: {tid}.{field}")
            if t["required_fields"] != [f["path"] for f in d["required_fields"]]:
                raise ValueError(f"Stale required fields: {tid}")
            self.templates[tid] = t
            self._definitions[tid] = d
            preset_ids = set()
            for p in t["presets"]:
                pid = p["preset_id"]
                if pid in preset_ids:
                    raise ValueError(f"Duplicate preset: {tid}/{pid}")
                preset_ids.add(pid)
                pd = self._approved_json(p["path"], p["sha256"])
                if pd["template_id"] != tid or pd["preset_id"] != pid:
                    raise ValueError(f"Preset identity mismatch: {tid}/{pid}")
                for field in ("name", "version", "keywords", "aliases"):
                    if pd[field] != p[field]:
                        raise ValueError(f"Stale preset index: {tid}/{pid}.{field}")
                self.presets[tid, pid] = p
                self._preset_definitions[tid, pid] = pd
            if preset_ids != set(d["presets"]):
                raise ValueError(f"Preset membership mismatch: {tid}")
        if not self.templates:
            raise ValueError("Empty Generic Library")
        self.style = self._approved_json("style/House_Style_Guide.json",
                                         self.index["style_guide_sha256"])
        if self.style["version"] != self.index["style_guide_version"]:
            raise ValueError("Style guide version mismatch")
        self.terms = self.keyword_index["terms"]
        for term, targets in self.terms.items():
            for target in targets:
                tid, pid = target["template_id"], target["preset_id"]
                if tid not in self.templates or (pid is not None and (tid, pid) not in self.presets):
                    raise ValueError(f"Dangling keyword target: {term}, {tid}/{pid}")

    def safe_path(self, rel):
        path = (self.root / rel).resolve()
        if not path.is_relative_to(self.root) or not path.is_file():
            raise ValueError(f"Missing or unsafe Generic Library path: {rel}")
        return path

    def _approved_json(self, rel, expected):
        path = self.safe_path(rel)
        actual = _sha(path)
        if actual != expected or self.approved.get(rel, {}).get("sha256") != actual:
            raise ValueError(f"Approval/index hash mismatch: {rel}")
        return _read(path)

    def template(self, template_id):
        """Authoritative approved structural definition, not a reference DOCX."""
        from copy import deepcopy
        return deepcopy(self._definitions[template_id])

    def preset(self, template_id, preset_id):
        from copy import deepcopy
        return deepcopy(self._preset_definitions[template_id, preset_id])

    def summary(self):
        from collections import Counter
        return {
            "templates": len(self.templates), "presets": len(self.presets),
            "keyword_terms": len(self.terms),
            "by_type": dict(Counter(t["output_type"] for t in self.templates.values())),
            "style_guide_version": self.style["version"],
            "approval_verified": True,
        }


def load_generic_library(root):
    return GenericLibrary(root)
