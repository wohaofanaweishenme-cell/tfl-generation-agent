"""Offline regression checks for one-call Step 2 targeted completion.

Uses the synthetic SAP bundled in the repository; no external API or
private target-study data is included or transmitted.
"""
import copy
import json
from pathlib import Path

from tfl_agent.agent.step1_parser import parse_inputs
from tfl_agent.agent.step2_spec_builder import build_specification

ROOT = Path(__file__).resolve().parents[1]
GROUPS = "/statistical_requirements/treatment_groups"
ROWS = "/table_requirements/row_requirements"


class ThreeCallClient:
    def __init__(self, planner, extraction, completion):
        self.planner = planner
        self.extraction = extraction
        self.completion = completion
        self.calls = []

    def json(self, system, user):
        self.calls.append(system.splitlines()[0])
        if "QUERY_PLANNER" in system:
            return self.planner
        if "EVIDENCE_COMPLETION" in system:
            payload = json.loads(user)
            assert GROUPS in payload["missing_fields"]
            assert ROWS in payload["missing_fields"]
            assert payload["candidate_blocks"]
            return self.completion
        if "EVIDENCE_EXTRACTOR" in system:
            return self.extraction
        raise AssertionError("Unexpected prompt")


def sample():
    fixture = json.loads((ROOT / "examples" / "demo_llm_output.json").read_text())
    raw = copy.deepcopy(fixture["extraction"])
    raw["statistical_requirements"]["treatment_groups"] = []
    raw["table_requirements"]["row_requirements"] = []
    raw["claims"] = [c for c in raw["claims"]
                     if not c["json_pointer"].startswith((GROUPS + "/", ROWS + "/"))]
    repair = {
        "statistical_requirements": {"treatment_groups":
            fixture["extraction"]["statistical_requirements"]["treatment_groups"]},
        "table_requirements": {"row_requirements":
            fixture["extraction"]["table_requirements"]["row_requirements"]},
        "claims": [c for c in fixture["extraction"]["claims"]
                   if c["json_pointer"].startswith((GROUPS + "/", ROWS + "/"))],
        "issues": [],
    }
    sap, targets, _ = parse_inputs(
        ROOT / "input" / "synthetic_sap.pdf",
        tfl_id="14.2.1", title="Summary of Overall Survival",
    )
    return sap, targets[0], fixture, raw, repair


def test_completion_recovers_missing_fields_with_verified_sap_quotes():
    sap, tfl, fixture, raw, repair = sample()
    llm = ThreeCallClient({"queries": fixture["queries"]}, raw, repair)
    spec, debug = build_specification(tfl, sap, llm, ROOT / "prompts")
    assert len(llm.calls) == 3
    assert spec["statistical_requirements"]["treatment_groups"] == ["Arm A", "Arm B"]
    assert spec["table_requirements"]["row_requirements"] == [
        "Median OS (months)", "95% CI"
    ]
    assert spec["readiness"] != "blocked"
    assert debug["completion"]["attempted"]
    assert set(debug["completion"]["verified_filled_fields"]) == {GROUPS, ROWS}
    links = [x["json_pointer"] for x in spec["provenance"]["field_links"]]
    assert GROUPS + "/0" in links and ROWS + "/0" in links


def test_completion_rejects_unverified_repair_quotes():
    sap, tfl, fixture, raw, repair = sample()
    for claim in repair["claims"]:
        claim["exact_quote"] = "FAKE QUOTATION THAT DOES NOT EXIST IN THE SAP"
    llm = ThreeCallClient({"queries": fixture["queries"]}, raw, repair)
    spec, debug = build_specification(tfl, sap, llm, ROOT / "prompts")
    assert len(llm.calls) == 3
    assert debug["completion"]["attempted"]
    assert spec["readiness"] == "blocked"
    assert spec["statistical_requirements"]["treatment_groups"] == []
    assert spec["table_requirements"]["row_requirements"] == []
    assert debug["completion"]["verified_filled_fields"] == []
    assert set(debug["completion"]["missing_after"]) == {GROUPS, ROWS}


def test_repair_does_not_override_validated_fields():
    sap, tfl, fixture, raw, repair = sample()
    repair["statistical_requirements"]["analysis_population"] = ["Imaginary Group"]
    repair["table_requirements"]["footnote_requirements"] = ["Fake footnote"]
    llm = ThreeCallClient({"queries": fixture["queries"]}, raw, repair)
    spec, debug = build_specification(tfl, sap, llm, ROOT / "prompts")
    assert spec["statistical_requirements"]["analysis_population"] == ["ITT"]
    assert "Fake footnote" not in spec["table_requirements"]["footnote_requirements"]
    assert "Imaginary Group" not in spec["statistical_requirements"]["analysis_population"]
