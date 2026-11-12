"""One bounded, evidence-checked completion pass for missing required SAP fields.

This module never fills requirements from a template library and never accepts
a repaired value without a verifiable quotation from the target SAP. It may
make ONE additional LLM API call after the standard two-call extraction.
"""
from copy import deepcopy
import json
from pathlib import Path

from tfl_agent.tools.sap_search import SAPIndex


def _required_missing(tfl, spec):
    from tfl_agent.agent.step2_spec_builder import (
        BASE_ESSENTIAL, ENDPOINT_ESSENTIAL, _get_pointer,
        _is_descriptive_table,
    )
    essentials = list(BASE_ESSENTIAL)
    if not _is_descriptive_table(tfl["title"]):
        essentials.insert(0, ENDPOINT_ESSENTIAL)
    missing = []
    for path in essentials:
        try:
            value = _get_pointer(spec, path)
        except (KeyError, IndexError, TypeError, ValueError):
            value = None
        if not value:
            missing.append(path)
    return missing


def _completion_queries(tfl, missing):
    queries = [tfl["title"], "study statistical analysis by treatment group"]
    if any(p.endswith("/treatment_groups") for p in missing):
        queries.extend([
            "study design treatment group dose arm randomized",
            "treatment groups dose cohorts study drug",
            "Group 1 Group 2 treatment assignment",
        ])
    if any(p.endswith("/row_requirements") for p in missing):
        queries.extend([
            "demographic and baseline characteristics age race height weight",
            "baseline characteristics variables disease characteristics",
            "summary table variables descriptive statistics",
        ])
    if any(p.endswith("/column_requirements") for p in missing):
        queries.extend(["summary by treatment groups and overall", "analysis population summary columns"])
    if any(p.endswith("/analysis_population") for p in missing):
        queries.extend(["analysis populations safety analysis set ITT PP", "demographic summaries based on analysis set"])
    if any(p.endswith("/analysis_methods") or p.endswith("/statistics_to_display") for p in missing):
        queries.extend(["statistical methods continuous categorical descriptive mean median frequency",
                        "Kaplan Meier survival analysis confidence interval"])
    return list(dict.fromkeys(queries))


def _candidate_relevance(block, missing):
    text = block.get("text", "").lower()
    score = 0
    if any(p.endswith("/treatment_groups") for p in missing):
        score += 3 * any(x in text for x in ("dose", "randomiz", "treatment group", "group 1", "group 2"))
    if any(p.endswith("/row_requirements") for p in missing):
        score += 3 * any(x in text for x in ("demographic", "baseline characteristic", "disease characteristic",
                                                "age", "race", "height", "weight"))
    if any(p.endswith("/column_requirements") for p in missing):
        score += 2 * any(x in text for x in ("by treatment group", "overall", "group 1", "group 2"))
    if any(p.endswith("/analysis_population") for p in missing):
        score += 2 * any(x in text for x in ("safety analysis", "intent-to-treat", "itt", "per protocol"))
    if any(p.endswith("/analysis_methods") or p.endswith("/statistics_to_display") for p in missing):
        score += 2 * any(x in text for x in ("median", "mean", "standard deviation", "kaplan", "confidence"))
    return score


def _merge_completion(raw, completion, missing):
    """Merge only missing top-level field values; ignore unrelated LLM changes.

    Their claims are merged only for corresponding child JSON pointers. The
    complete result is later revalidated against original target-SAP blocks.
    """
    merged = deepcopy(raw)
    accepted = []
    for path in missing:
        parts = path.strip("/").split("/")
        if len(parts) != 2:
            continue
        section, field = parts
        existing = merged.get(section, {}).get(field)
        if isinstance(existing, str) and existing.strip() or isinstance(existing, list) and existing:
            # Earlier raw data may have been nonempty but rejected as unsupported.
            # Replacing those unverified strings is allowed, but never changes a
            # value that survived the first verified specification (checked by caller).
            pass
        proposed = completion.get(section, {}).get(field) if isinstance(completion.get(section), dict) else None
        if isinstance(proposed, list):
            proposed = [v for v in proposed if isinstance(v, str) and v.strip()][:30]
            if not proposed:
                continue
        elif not isinstance(proposed, str) or not proposed.strip():
            continue
        merged.setdefault(section, {})[field] = proposed
        accepted.append(path)
    claims = merged.get("claims", [])
    claims = [c for c in claims if isinstance(c, dict) and not any(
        c.get("json_pointer", "") == p or c.get("json_pointer", "").startswith(p + "/")
        for p in accepted
    )]
    for claim in completion.get("claims", []):
        if not isinstance(claim, dict):
            continue
        path = claim.get("json_pointer", "")
        if isinstance(path, str) and any(path == p or path.startswith(p + "/") for p in accepted):
            claims.append(claim)
    merged["claims"] = claims
    # Keep original issues for the audit; mark them resolved only after evidence
    # verification successfully populated the respective field.
    return merged, accepted


def complete_required_fields(tfl, sap, llm, prompts_dir, raw, initial_spec, candidates):
    """Attempt one focused completion when required fields are absent.

    Returns (specification, audit). All additions pass through the existing
    quote/pointer and target-population validation; there is no fixture fallback.
    """
    from tfl_agent.agent.step2_spec_builder import (
        build_specification_from_extraction, _get_pointer,
    )
    missing = _required_missing(tfl, initial_spec)
    audit = {
        "attempted": False, "missing_before": missing,
        "missing_after": missing, "accepted_fields": [],
        "verified_filled_fields": [], "candidate_block_ids": [],
        "raw_completion": None,
    }
    if not missing:
        return initial_spec, audit

    queries = _completion_queries(tfl, missing)
    extra_blocks = SAPIndex(sap).search(queries, top_k=24)
    # Preserve all blocks used by first pass for future citation verification.
    by_id = {b["block_id"]: b for b in candidates}
    for block in extra_blocks:
        by_id[block["block_id"]] = block

    # Prioritise relevant paragraphs while keeping a small, bounded prompt.
    ranking = sorted(
        extra_blocks,
        key=lambda b: (-_candidate_relevance(b, missing), b["page"], b["block_id"]),
    )
    prompt_blocks = ranking[:30]
    for block in candidates:
        if len(prompt_blocks) >= 36:
            break
        if block["block_id"] not in {x["block_id"] for x in prompt_blocks}:
            prompt_blocks.append(block)
    prompt_file = Path(prompts_dir) / "03_complete_missing_fields.txt"
    completion_prompt = prompt_file.read_text(encoding="utf-8")
    payload = {
        "tfl": tfl,
        "missing_fields": missing,
        "current_verified_specification": initial_spec["statistical_requirements"]
        | {"table_requirements": initial_spec["table_requirements"]},
        "candidate_blocks": prompt_blocks,
    }
    completion = llm.json(completion_prompt, json.dumps(payload, ensure_ascii=False))
    if not isinstance(completion, dict):
        raise ValueError("Completion LLM response must be a JSON object")
    audit["attempted"] = True
    audit["candidate_block_ids"] = [b["block_id"] for b in prompt_blocks]
    audit["raw_completion"] = completion
    merged, accepted = _merge_completion(raw, completion, missing)
    audit["accepted_fields"] = accepted
    if not accepted:
        return initial_spec, audit

    # All first-pass verified fields are retained. The missing fields must
    # acquire valid per-field citations before they can survive normalization.
    verified_spec = build_specification_from_extraction(tfl, sap, merged, list(by_id.values()))
    still_missing = _required_missing(tfl, verified_spec)
    audit["missing_after"] = still_missing
    audit["verified_filled_fields"] = [p for p in accepted if p not in still_missing]

    for issue in verified_spec["issues"]:
        if (issue["issue_type"] == "missing"
                and issue["json_pointer"] in audit["verified_filled_fields"]):
            issue["status"] = "resolved"
            issue["description"] += " [resolved by cited Step 2 completion]"
    if not still_missing:
        verified_spec["readiness"] = (
            "needs_review" if any(i["status"] == "open" for i in verified_spec["issues"])
            else "ready"
        )
    return verified_spec, audit
