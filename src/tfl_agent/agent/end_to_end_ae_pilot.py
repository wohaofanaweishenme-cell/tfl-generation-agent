"""One-PDF entrypoint: SAP → AE Spec → Library retrieval → Plan → DOCX → QA.

Notebook owns only upload, parameters, invocation, display and download.
All extraction and construction are packaged in GitHub's tfl_agent code.
"""
from __future__ import annotations
import copy
import json
from pathlib import Path

from tfl_agent.tools.pdf_parser import parse_sap
from tfl_agent.tools.library_loader import load_library
from tfl_agent.agent.step3_retriever import retrieve_templates
from tfl_agent.agent.adaptation_planner import build_adaptation_plan
from tfl_agent.agent.ae_spec_extractor import (
    extract_ae_spec_from_sap, _authorized_blocks,
)
from tfl_agent.agent.reconstruction_blueprint import build_reconstruction_blueprint
from tfl_agent.agent.blueprint_docx_generator import (
    generate_docx_from_blueprint, validate_reconstructed_shell,
)
from tfl_agent.tools.io_utils import write_json


def run_single_sap_ae_pilot(
    sap_path: str | Path, library_path: str | Path,
    output_dir: str | Path, *, parsed_override: dict | None = None
) -> dict:
    """Single-call end-to-end AE pilot. parsed_override is for tests only."""
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    parsed = (
        copy.deepcopy(parsed_override) if parsed_override is not None
        else parse_sap(sap_path)
    )
    spec, extraction = extract_ae_spec_from_sap(parsed)
    libroot = Path(library_path).resolve()
    library = load_library(libroot)
    index_file = libroot / "Template_Index.json"
    registry_file = libroot / "Library_Registry.json"
    if not index_file.is_file() or not registry_file.is_file():
        raise FileNotFoundError("Official Library index and registry are required")
    index = {
        r["template_id"]: r
        for r in json.loads(index_file.read_text(encoding="utf-8"))["entries"]
    }
    approved_ids = {
        tid for tid, record in index.items()
        if record.get("review_status") == "approved"
        and record.get("formal_use_eligible") is True
    }
    candidates = []
    for t in library["templates"]:
        tid = t["identity"]["template_id"]
        if tid not in approved_ids:
            continue
        indexed = index[tid]
        locator = (libroot.parent / indexed["locator_map_path"]).resolve()
        if not locator.is_file() or not locator.is_relative_to(libroot):
            continue
        t["locator_map_path"] = str(locator)
        candidates.append(t)
    library["templates"] = candidates
    if not candidates:
        raise ValueError("Approved Library has no locator-backed templates")

    ranking = retrieve_templates(spec, library, top_k=8)
    if not ranking:
        raise ValueError("No official AE Table candidate found")
    source = next((
        x for x in ranking
        if not x.get("cross_endpoint")
        and not x.get("requires_endpoint_review")
    ), ranking[0])
    page_range = tuple(extraction["body_page_range"])
    body = {**parsed, "blocks": _authorized_blocks(parsed, page_range)}
    plan = None
    plan_failure = None
    if not source.get("cross_endpoint") and not source.get("requires_endpoint_review"):
        try:
            plan = build_adaptation_plan(
                spec, source,
                parsed_sap_blocks=body,
                sap_body_page_range=page_range,
            )
        except Exception as exc:
            # The study-specific diagnostic bookmark plan is optional.
            # Structural rebuild does NOT wait for manual approval or depend
            # on source-clinical equivalence.
            plan_failure = f"{type(exc).__name__}: {exc}"
    else:
        plan_failure = (
            "Source has different known endpoint; used only for visual styling"
        )

    final_docx = out / (
        f"Table_{spec['identity']['tfl_id']}_AE_STRUCTURAL_SHELL_DRAFT.docx"
    )
    # The diagnostic Plan now feeds the actual generation Blueprint.
    # On incompatible/unverified sources, use a target-only layout rather
    # than silently transferring unrelated source-study clinical content.
    blueprint = build_reconstruction_blueprint(spec, adaptation_plan=plan)
    generated = generate_docx_from_blueprint(
        blueprint, final_docx,
        style_source=(source["source_path"] if plan else None),
    )
    verified = validate_reconstructed_shell(final_docx, blueprint)
    rebuild_plan = {
        "plan_type": "source_ir_guided_target_blueprint_rebuild_mvp",
        "blueprint_version": blueprint["blueprint_version"],
        "verified_source_structure_used": blueprint["source_structure"]["verified_source_ir_used"],
        "requires_manual_approval_to_generate": False,
        "clinical_approval": False,
        "source_template_reference": source["template_id"],
        "target_tfl_id": spec["identity"]["tfl_id"],
        "target_word_columns": [
            "Adverse Event Category",
            *spec["statistical_requirements"]["treatment_groups"], "Overall",
        ],
        "target_word_rows": spec["table_requirements"]["row_requirements"],
        "statistics_per_treatment": ["Patient count n", "Percent", "Event count"],
        "placeholder_text": "xx (xx.x%) | xx",
        "footnotes": spec["table_requirements"]["footnote_requirements"],
        "source_study_content_copied": False,
        "unresolved_requirements": extraction["unresolved"],
        "steps": [
            "LOAD_VERIFIED_SOURCE_IR_WHEN_COMPATIBLE",
            "MERGE_TARGET_LAYOUT_IR_WITH_SOURCE_PRESENTATION_PATTERN",
            "WRITE_RECONSTRUCTION_BLUEPRINT_JSON",
            "GENERATE_EDITABLE_NATIVE_WORD_TABLE_FROM_BLUEPRINT",
            "RUN_BLUEPRINT_STRUCTURAL_VALIDATION",
        ],
    }
    diagnostics = {
        "status": (
            "structural_draft_generated" if verified["valid_structural_shell"]
            else "structural_validation_failed"
        ),
        "source_sap": Path(sap_path).name,
        "input_file_count": 1,
        "target_id": spec["identity"]["tfl_id"],
        "approved_library_count": len(candidates),
        "top_5_retrieval": [{
            "template_id": x["template_id"],
            "source_study_id": x.get("source_study_id"),
            "score": x["score"],
            "requires_endpoint_review": x.get("requires_endpoint_review"),
        } for x in ranking[:5]],
        "chosen_style_template_id": source["template_id"],
        "blueprint_version": blueprint["blueprint_version"],
        "source_structure_used": generated["source_structure_used"],
        "steps": [
            "Parse 1 Drive-linked SAP PDF (text blocks)",
            "Extract one AE Specification from body sections using rules",
            "Retrieve approved editable source DOCX templates",
            "Construct a diagnostic Adaptation Plan, when compatible",
            "Reconstruct target AE Word directly from source-aware Blueprint",
            "Validate Word structure and source-content isolation",
        ],
        "manual_adaptation_review_required_to_generate": False,
        "adaptation_plan_reviewed_or_approved": False,
        "adaptation_plan_status": (plan or {}).get(
            "planning_status", "not_available"
        ),
        "adaptation_plan_error": plan_failure,
        "extraction": extraction,
        "generation": generated,
        "validation": verified,
        "warnings": [
            "One SAP and zero approvals yields a draft, not a clinically validated TFL.",
            "This MVP only implements an Overall AE Table.",
            "The approved Library is read-only; source clinical rows/footnotes are not copied.",
        ],
    }
    write_json(out / "TFL_Specification.json", spec)
    write_json(out / "TFL_Inventory.json", [{
        "tfl_id": spec["identity"]["tfl_id"],
        "title": spec["identity"]["title"],
        "output_type": "table",
    }])
    write_json(out / "Template_Retrieval.json", diagnostics["top_5_retrieval"])
    write_json(out / "SAP_Extraction_Evidence.json", extraction)
    write_json(out / "Automatic_Structural_Adaptation_Plan.json", rebuild_plan)
    write_json(out / "Reconstruction_Blueprint.json", blueprint)
    if plan:
        write_json(out / "Adaptation_Plan.json", plan)
    write_json(out / "Generation_Rationale.json", diagnostics)
    write_json(out / "Validation_Report.json", verified)
    if not verified["valid_structural_shell"]:
        raise AssertionError(
            "Generated Word does not match extracted target AE layout: "
            + repr(verified["structural_errors"])
        )
    return diagnostics
