"""One-SAP, one-Table reconstruction using an existing target Specification.

This is the generic Step 4 path. For SAP-only automatic AE extraction use
run_single_sap_ae_pilot. New study SAPs are supplied by a path, not uploaded.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from tfl_agent.agent.adaptation_planner import build_adaptation_plan
from tfl_agent.agent.blueprint_docx_generator import (
    generate_docx_from_blueprint, validate_reconstructed_shell,
)
from tfl_agent.agent.reconstruction_blueprint import build_reconstruction_blueprint
from tfl_agent.agent.step3_retriever import retrieve_templates
from tfl_agent.tools.io_utils import write_json
from tfl_agent.tools.library_loader import load_library
from tfl_agent.tools.pdf_parser import parse_sap


def _official_library(library_path):
    libroot = Path(library_path).resolve()
    library = load_library(libroot)
    index_file = libroot / "Template_Index.json"
    registry_file = libroot / "Library_Registry.json"
    if not index_file.is_file() or not registry_file.is_file():
        raise FileNotFoundError("Approved official Library index/registry missing")
    index = {item["template_id"]: item for item in
             json.loads(index_file.read_text(encoding="utf-8"))["entries"]}
    approved = []
    for item in library["templates"]:
        tid = item["identity"]["template_id"]
        record = index.get(tid) or {}
        if not (record.get("review_status") == "approved"
                and record.get("formal_use_eligible") is True):
            continue
        relative = record.get("locator_map_path")
        if not relative:
            continue
        locator = (libroot.parent / relative).resolve()
        if not locator.is_file() or not locator.is_relative_to(libroot):
            continue
        item["locator_map_path"] = str(locator)
        approved.append(item)
    if not approved:
        raise ValueError("No verified editable templates in official Library")
    library["templates"] = approved
    return library


def run_table_blueprint_from_spec(
    *, sap_path: str | Path, spec_path: str | Path,
    library_path: str | Path, output_dir: str | Path,
    sap_body_page_range: tuple[int, int] | None = None,
) -> dict:
    """Reconstruct a target Table from a Drive-supplied SAP + target Spec JSON.

    Does not auto-extract Demographics/Disposition specs. The caller must supply
    an independent target SAP-derived Spec (for example the saved Step 2 JSON).
    No source-study clinical content is borrowed.
    """
    sap_path, spec_path = Path(sap_path), Path(spec_path)
    if not sap_path.is_file() or not spec_path.is_file():
        raise FileNotFoundError("Both the SAP PDF and target Spec JSON must exist")
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    if spec.get("identity", {}).get("output_type") != "table":
        raise ValueError("General Blueprint MVP supports Table only")
    parsed = parse_sap(sap_path)
    if sap_body_page_range is not None:
        lo, hi = sap_body_page_range
        if not (isinstance(lo, int) and isinstance(hi, int) and
                1 <= lo <= hi <= parsed.get("pages", 0)):
            raise ValueError("Invalid authorized SAP-body page range")
        body = {**parsed, "blocks": [
            b for b in parsed.get("blocks") or []
            if lo <= b.get("page", 0) <= hi
        ]}
    else:
        body = None  # Do NOT pass full SAP: it may contain held-out TFL shells.

    library = _official_library(library_path)
    ranking = retrieve_templates(spec, library, top_k=8)
    if not ranking:
        raise ValueError("No official compatible output-type candidate found")
    plan, plan_error, chosen = None, None, None
    for candidate in ranking:
        if candidate.get("cross_endpoint") or candidate.get("requires_endpoint_review"):
            continue
        try:
            plan = build_adaptation_plan(
                spec, candidate,
                parsed_sap_blocks=body,
                sap_body_page_range=sap_body_page_range if body else None,
            )
            chosen = candidate
            break
        except (ValueError, FileNotFoundError, KeyError) as exc:
            plan_error = f"{type(exc).__name__}: {exc}"
    if chosen is None:
        chosen = ranking[0]

    blueprint = build_reconstruction_blueprint(spec, adaptation_plan=plan)
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    tfl_id = str(spec["identity"]["tfl_id"])
    safe_id = re.sub(r"[^A-Za-z0-9._-]+", "_", tfl_id)
    final_docx = out / f"Table_{safe_id}_BLUEPRINT_DRAFT.docx"
    result = generate_docx_from_blueprint(
        blueprint, final_docx, style_source=(
            chosen["source_path"] if plan else None
        )
    )
    report = validate_reconstructed_shell(final_docx, blueprint)
    summary = {
        "status": "structural_draft_generated" if report["valid_structural_shell"]
                  else "structural_validation_failed",
        "source_sap": sap_path.name,
        "source_specification": spec_path.name,
        "source_spec_supplied_separately": True,
        "approved_library_count": len(library["templates"]),
        "target_id": tfl_id,
        "retrieved_template_id": chosen["template_id"],
        "source_structure_used": result["source_structure_used"],
        "adaptation_plan_error": plan_error,
        "spec_evidence_checked_against_sap_body": body is not None,
        "generation": result,
        "validation": report,
        "warnings": [
            "A separately supplied target Specification is required for non-AE Tables.",
            "Ground-truth and clinical correctness are NOT verified.",
            "No source-study clinical content is copied.",
        ],
    }
    write_json(out / "TFL_Specification.json", spec)
    write_json(out / "Template_Retrieval.json", [{
        "template_id": item["template_id"],
        "score": item["score"],
        "source_study_id": item.get("source_study_id"),
        "cross_endpoint": item.get("cross_endpoint"),
    } for item in ranking[:5]])
    write_json(out / "Reconstruction_Blueprint.json", blueprint)
    if plan:
        write_json(out / "Adaptation_Plan.json", plan)
    write_json(out / "Generation_Rationale.json", summary)
    write_json(out / "Validation_Report.json", report)
    if not report["valid_structural_shell"]:
        raise AssertionError("Generated Word fails Blueprint structural validation: "
                             + repr(report["structural_errors"]))
    return summary
