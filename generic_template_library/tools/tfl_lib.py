"""Shared helpers for the generic template library tools (paths, JSON, hashing, schema validation)."""
import hashlib
import json
import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCHEMAS = os.path.join(ROOT, "schemas")
TEMPLATES = os.path.join(ROOT, "templates")
PRESETS = os.path.join(ROOT, "presets")
STYLE = os.path.join(ROOT, "style", "House_Style_Guide.json")
INVENTORY = os.path.join(ROOT, "inventory")


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def dump(obj, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        h.update(fh.read())
    return h.hexdigest()


def rel(path):
    return os.path.relpath(path, ROOT)


def validator(schema_name):
    from jsonschema import Draft202012Validator
    schema = load(os.path.join(SCHEMAS, schema_name))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def schema_errors(schema_name, obj):
    v = validator(schema_name)
    return [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}" for e in v.iter_errors(obj)]


def template_files():
    out = []
    for typ in ("table", "listing", "figure"):
        d = os.path.join(TEMPLATES, typ)
        if os.path.isdir(d):
            out += [os.path.join(d, f) for f in sorted(os.listdir(d)) if f.endswith(".json")]
    return out


def preset_files(template_id):
    d = os.path.join(PRESETS, template_id)
    if not os.path.isdir(d):
        return []
    return [os.path.join(d, f) for f in sorted(os.listdir(d)) if f.endswith(".json")]


def norm(text):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9%+]+", " ", (text or "").lower())).strip()


def source_library():
    """Locate the original (read-only) source Library next to this folder.

    Order: $TFL_SOURCE_LIBRARY, ../library (GitHub repository layout), ../Library (local workspace).
    Returns the Library root (the folder that contains studies/ and Template_Index.json)."""
    cands = [os.environ.get("TFL_SOURCE_LIBRARY"), os.path.join(ROOT, "..", "library"), os.path.join(ROOT, "..", "Library")]
    for c in cands:
        if c and os.path.isdir(os.path.join(c, "studies")):
            return os.path.abspath(c)
    raise SystemExit("Source Library not found; set TFL_SOURCE_LIBRARY to the folder that contains studies/.")
