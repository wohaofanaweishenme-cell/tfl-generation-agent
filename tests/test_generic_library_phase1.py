"""Read-only integration checks on the checked-in Generic Library."""
import json
from pathlib import Path

import pytest

from tfl_agent.tools.generic_library import load_generic_library
from tfl_agent.agent.generic_retriever import retrieve_generic_baseline, entry_from_spec
from tfl_agent.agent.generic_evaluation import evaluate

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def library():
    return load_generic_library(ROOT / "generic_template_library")


def test_approved_snapshot(library):
    s = library.summary()
    assert s["templates"] == 16
    assert s["presets"] == 66
    assert s["keyword_terms"] == 316
    assert s["by_type"] == {"table": 9, "listing": 1, "figure": 6}
    assert s["approval_verified"]
    assert library.preset("TBL_VARIABLE_SUMMARY", "demographics")["default_status"] == "needs_review"


def test_unsafe_path(library):
    with pytest.raises(ValueError, match="unsafe"):
        library.safe_path("../README.md")


@pytest.mark.parametrize("title,kind,template,preset", [
    ("Demographic and Baseline Characteristics", "table", "TBL_VARIABLE_SUMMARY", "demographics"),
    ("Treatment-emergent adverse events by System Organ Class and Preferred Term", "table",
     "TBL_CODED_TERM_HIERARCHY", "teae_soc_pt"),
    ("Kaplan-Meier Plot of Overall Survival", "figure", "FIG_KAPLAN_MEIER", "overall_survival"),
])
def test_baseline_cases(library, title, kind, template, preset):
    r = retrieve_generic_baseline({"original_title": title, "output_type": kind}, library)
    assert r["template_id"] == template
    assert r["preset_id"] == preset
    assert r["generation_authorized"] is False
    assert r["sap_evidence_used"] is False
    assert all(library.templates[c["template_id"]]["output_type"] == kind for c in r["candidates"])


def test_legacy_spec_bridge(library):
    spec = {"identity": {"tfl_id": "14.1.2", "title": "Demographic and Baseline Characteristics",
                         "output_type": "table"}}
    entry = entry_from_spec(spec)
    assert entry["original_tfl_number"] == "14.1.2"
    assert "population" not in entry
    assert retrieve_generic_baseline(entry, library)["template_id"] == "TBL_VARIABLE_SUMMARY"


def test_reproduce_published_benchmark(library):
    actual, _ = evaluate(ROOT, library)
    expected = json.loads((library.root / "qa/matching_eval/Summary.json").read_text())
    for field in ("entries_total", "with_ground_truth", "correct", "accuracy", "outcomes", "by_output_type"):
        assert actual[field] == expected[field], field
