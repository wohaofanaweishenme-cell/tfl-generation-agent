"""Phase 6.3.1: offline decision-protocol replay. No network or model invocation.

A rank-first recommendation is a hypothesis, not a supported selection.
Exact quote verification establishes provenance, not semantic applicability.
Evaluation labels are joined only after replay.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from collections import Counter
from pathlib import Path

from tfl_agent.agent.phase6_llm_pilot import validate_response, digest, PILOT, ARMS

ARCHIVE_SHA = "a82ab7c608aa370c60a2ba73f6ac4aff3b3fee6a9298e8f05c1427bf859b2c37"
ARCHIVE_NAME = "20261127T045311819056Z.zip"
VERSION = "6.3.1-v1"


def _id(x):
    return isinstance(x, str) and bool(x.strip())


def _unique_ids(xs, expected):
    return (isinstance(xs, list) and all(_id(x) for x in xs)
            and len(xs) == len(expected) and set(xs) == expected)


def replay_decision(obj, payload):
    """Normalize only the uncertain-selection protocol mismatch; fail closed otherwise.

    Ranking is evaluated independently of citation/selection failures. A recommendation
    cannot authorize specification facts or generation. All candidate citations are audited,
    including alternatives. Presets are proposed separately and never assumed correct.
    """
    templates = {t["template_id"]: {p["preset_id"] for p in t["presets"]}
                 for t in payload["library"]["templates"]}
    chunks = {c["chunk_id"]: c["text"] for c in payload["sap_evidence"]}
    issues = []
    audit = []
    def fail(code):
        if code not in issues:
            issues.append(code)

    if not isinstance(obj, dict):
        obj = {}
        fail("response_not_object")
    ranking = obj.get("ranking")
    ranking_valid = _unique_ids(ranking, set(templates))
    if not ranking_valid:
        fail("invalid_complete_ranking")
    recommendation = ranking[0] if ranking_valid else None
    assessments = obj.get("candidate_assessments")
    by_id = {}
    if not isinstance(assessments, list):
        fail("invalid_assessments")
        assessments = []
    for a in assessments:
        if not isinstance(a, dict) or not _id(a.get("template_id")):
            fail("invalid_assessment_id")
            continue
        tid = a["template_id"]
        if tid not in templates or tid in by_id:
            fail("invalid_or_duplicate_assessment_id")
            continue
        by_id[tid] = a
        if a.get("compatibility") not in ("supported", "uncertain", "incompatible"):
            fail("invalid_compatibility")
        if not _id(a.get("reason")):
            fail("invalid_assessment_reason")
        missing = a.get("missing_information")
        if not isinstance(missing, list) or not all(isinstance(x, str) for x in missing):
            fail("invalid_missing_information")
        citations = a.get("citations")
        if not isinstance(citations, list):
            fail("invalid_citation_array")
            continue
        for i, c in enumerate(citations):
            source = None
            cid = None
            quote = None
            exact = False
            if isinstance(c, dict) and all(k in c for k in ("source", "chunk_id", "exact_quote")):
                source, cid, quote = c["source"], c["chunk_id"], c["exact_quote"]
                text = None
                if source == "title" and cid is None:
                    text = payload["target"]["title"]
                elif source == "sap" and _id(cid) and cid in chunks:
                    text = chunks[cid]
                exact = isinstance(text, str) and _id(quote) and quote in text
            if not exact:
                fail("invalid_exact_citation")
            audit.append({"template_id":tid, "citation_index":i, "source":source,
                          "chunk_id":cid, "exact_quote":quote, "exact_match":exact,
                          "applicability":"unreviewed"})
    if set(by_id) != set(templates):
        fail("incomplete_assessments")
    if not _id(obj.get("reason")):
        fail("invalid_selection_reason")
    if not all(k in obj for k in ("selected_template", "selected_preset", "selection_status")):
        fail("missing_selection_fields")
    selected, preset, status = (obj.get(k) for k in
                                 ("selected_template", "selected_preset", "selection_status"))
    if selected is not None and (not _id(selected) or selected not in templates):
        fail("unknown_selected_template")
    if selected is not None and selected != recommendation:
        fail("selection_not_rank_first")
    preset_owner = None
    if preset is not None:
        if not _id(preset) or not _id(selected) or preset not in templates.get(selected, set()):
            fail("invalid_preset_ownership")
        else:
            preset_owner = selected
    top = by_id.get(recommendation, {})
    compatibility = top.get("compatibility")
    if status == "candidate_only":
        if selected is None or compatibility != "supported" or not top.get("citations"):
            fail("unsupported_candidate_only")
    elif status == "uncertain":
        # Non-null selected_template is interpreted as a proposal only if it
        # is the rank-first eligible ID and the remaining response passes checks.
        # A preset alongside such a proposal is audited, never supported.
        if selected is None and preset is not None:
            fail("preset_without_selection")
    elif status == "no_compatible_template":
        if selected is not None or preset is not None:
            fail("invalid_no_compatible_abstention")
    else:
        fail("invalid_selection_status")
    protocol_repaired = not issues and status == "uncertain" and selected is not None
    supported = selected if not issues and status == "candidate_only" else None
    decision_status = ("invalid" if issues else "supported_candidate" if supported
                       else status)
    return {
        "ranking": ranking if ranking_valid else [],
        "ranking_valid": ranking_valid,
        "recommended_template": recommendation,
        "alternatives": ranking[1:] if ranking_valid else [],
        "recommendation_is_compatible": compatibility,
        "supported_template": supported,
        "proposed_preset": preset if not issues and preset_owner else None,
        "supported_preset": preset if supported and preset_owner == supported else None,
        "decision_status": decision_status,
        "original_selection_status": status,
        "original_selected_template": selected,
        "original_selected_preset": preset,
        "protocol_repaired": protocol_repaired,
        "protocol_valid": not issues,
        "uncertainty": status in ("uncertain", "no_compatible_template") or bool(issues),
        "missing_information": top.get("missing_information", []),
        "reason": obj.get("reason"),
        "issues": issues,
        "citation_audit": audit,
        "semantic_applicability_verified": False,
        "clinical_confirmation": False,
        "generation_authorized": False,
    }


def _strict(obj, payload):
    try:
        x = validate_response(obj, payload)
        return True, x["selected_template"], None
    except (ValueError, KeyError, TypeError, AttributeError, IndexError) as e:
        return False, None, str(e)


def _json(z, name):
    return json.loads(z.read(name))


def _sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_frozen(archive):
    """Read exact historical run; no extraction, mutable cache, or re-retrieval."""
    actual = _sha(archive)
    if actual != ARCHIVE_SHA:
        raise ValueError(f"Frozen archive SHA mismatch: {actual}")
    with zipfile.ZipFile(archive) as z:
        requests = _json(z, "Frozen_Requests.json")
        records = _json(z, "Raw_Responses.json")
        config = _json(z, "Experiment_Config.json")
        context = _json(z, "Decision_Context.json")
        summary = _json(z, "Summary.json")
        labels = list(csv.DictReader(io.StringIO(z.read("Pilot_Cases.csv").decode("utf-8-sig"))))
    expected = {f"{s}__{e}__{a}" for s,e in PILOT for a in ARMS}
    def index(seq):
        result = {x["request_id"]:x for x in seq}
        if len(seq) != 18 or set(result) != expected:
            raise ValueError("Incomplete or duplicate frozen request IDs")
        return result
    rq, rr = index(requests), index(records)
    if config["budget"] != 18 or summary["attempts_reserved"] != 18:
        raise ValueError("Unexpected original budget")
    for rid, req in rq.items():
        rec = rr[rid]
        if any(req[k] != rec[k] for k in ("study_id","entry_id","arm","fingerprint")):
            raise ValueError(f"Request/response mismatch: {rid}")
        if rid != f'{req["study_id"]}__{req["entry_id"]}__{req["arm"]}':
            raise ValueError("Identity mismatch")
        p = req["payload"]
        if p["library"] != context[p["target"]["output_type"]]:
            raise ValueError("Frozen context mismatch")
        if digest({"model":config["model"],"system":config["system"],"max_tokens":8192,
                   "temperature":0,"thinking":False,"payload":p}) != req["fingerprint"]:
            raise ValueError("Request fingerprint mismatch")
        if req["arm"] == "A_title" and p["sap_evidence"]:
            raise ValueError("Unexpected title-arm evidence")
        ts = p["library"]["templates"]
        if len(ts) != 9 or len({t["template_id"] for t in ts}) != 9:
            raise ValueError("Unexpected table candidate set")
        presets = [x["preset_id"] for t in ts for x in t["presets"]]
        if len(presets) != 32 or len(set(presets)) != 32:
            raise ValueError("Unexpected table preset set")
        cs = p["sap_evidence"]
        if len({c["chunk_id"] for c in cs}) != len(cs):
            raise ValueError("Duplicate SAP evidence IDs")
    lm = {(x["study_id"],x["entry_id"]):x for x in labels}
    if len(labels) != 6 or set(lm) != set(PILOT):
        raise ValueError("Pilot label identity mismatch")
    for req in requests:
        lab = lm[req["study_id"],req["entry_id"]]
        if lab["title"] != req["payload"]["target"]["title"] or lab["output_type"] != "table":
            raise ValueError("Target/label mismatch")
        if not set(lab["expected"].split("|")) <= {t["template_id"] for t in req["payload"]["library"]["templates"]}:
            raise ValueError("Label outside pilot candidate universe")
    return requests, rr, lm, summary


def _metrics(rows, field):
    n = len(rows)
    picked = sum(r[field] is not None for r in rows)
    correct = sum(r[field] in r["expected"].split("|") for r in rows)
    return {"n":n, "selected":picked, "correct":correct,
            "coverage":picked/n, "accuracy_all":correct/n,
            "accuracy_selected":correct/picked if picked else None}


def summarize(rows):
    out = {}
    for arm in (*ARMS, "all"):
        sub = [r for r in rows if r["arm"] == arm or arm == "all"]
        n = len(sub)
        ranks = [r["expected_rank"] for r in sub]
        out[arm] = {
            "n":n, "raw_ranking_valid":sum(r["ranking_valid"] for r in sub),
            "raw_top1":sum(x == 1 for x in ranks), "raw_recall_at_3":sum(x is not None and x <= 3 for x in ranks),
            "raw_mrr":sum(1/x for x in ranks if x)/n,
            "original_status_counts":dict(Counter(r["original_record_status"] for r in sub)),
            "original_strict_pass":sum(r["original_strict_valid"] for r in sub),
            "revised_protocol_pass":sum(r["protocol_valid"] for r in sub),
            "protocol_repairs":sum(r["protocol_repaired"] for r in sub),
            "revised_status_counts":dict(Counter(r["decision_status"] for r in sub)),
            "failure_counts":dict(Counter(i for r in sub for i in r["issues"])),
            "original_strict_selection":_metrics(sub,"original_strict_selected"),
            "revised_recommendation":_metrics(sub,"recommended_template"),
            "revised_supported_selection":_metrics(sub,"supported_template"),
            "no_compatible_abstentions":sum(r["decision_status"]=="no_compatible_template" for r in sub),
            "citation_exact_pass":sum(c["exact_match"] for r in sub for c in r["citation_audit"]),
            "citation_count":sum(len(r["citation_audit"]) for r in sub),
        }
    return out


def run_replay(archive, out):
    requests, records, labels, prior = load_frozen(archive)
    rows = []
    for req in requests:
        rec = records[req["request_id"]]
        parsed = None
        parse_error = None
        if rec.get("finish_reason") != "stop":
            parse_error = "non_stop_finish"
        else:
            try:
                parsed = json.loads(rec["raw_response"])
            except (KeyError, TypeError, ValueError):
                parse_error = "invalid_raw_json"
        d = replay_decision(parsed, req["payload"])
        if parse_error:
            d["issues"].append(parse_error)
            d["protocol_valid"] = False
        strict, strict_selected, strict_error = _strict(parsed, req["payload"])
        if parse_error:
            strict, strict_selected, strict_error = False, None, parse_error
        if strict != (rec["status"] == "valid"):
            raise ValueError(f'Original strict replay drift: {req["request_id"]}')
        if strict and strict_selected != rec["output"]["selected_template"]:
            raise ValueError("Original strict selected ID drift")
        # Gold joins only here: no label consulted in replay_decision.
        label = labels[req["study_id"],req["entry_id"]]
        expected = label["expected"]
        rank = next((i for i,t in enumerate(d["ranking"],1) if t in expected.split("|")),None)
        rows.append({**d,"request_id":req["request_id"],"fingerprint":req["fingerprint"],
                     "study_id":req["study_id"],"entry_id":req["entry_id"],"arm":req["arm"],
                     "title":req["payload"]["target"]["title"],"expected":expected,
                     "expected_rank":rank,"original_record_status":rec["status"],
                     "original_error":rec.get("error"),"original_strict_error":strict_error,
                     "original_strict_valid":strict,"original_strict_selected":strict_selected,
                     "finish_reason":rec.get("finish_reason"),"original_usage":rec.get("usage")})
    report = {"version":VERSION,"source_archive_sha256":ARCHIVE_SHA,"new_llm_calls":0,
              "historical_pilot_attempts":prior["attempts_reserved"],
              "historical_recorded_usage":prior["recorded_usage"],
              "generation_authorized":False,"clinical_confirmation":False,
              "preset_accuracy":None,"metrics":summarize(rows),
              "caveats":["Development cases only; no independent validation.",
                         "Recommendation equals rank-first; no ranking improvement is claimed.",
                         "Supported candidate means protocol and exact provenance checks only; semantic applicability is unverified.",
                         "Uncertain proposals remain unsupported; no compatible status remains an abstention.",
                         "No independent preset labels."]}
    out = Path(out)
    out.mkdir(parents=True,exist_ok=False)
    def save(name, value):
        (out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    def write(name, records, fields):
        with (out/name).open("w",encoding="utf-8",newline="") as f:
            w = csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
            w.writeheader()
            for r in records:
                w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in r.items()})
    save("Summary.json",report)
    save("Replayed_Decisions.json",rows)
    write("Decision_Replay.csv",rows,[k for k in rows[0] if k!="citation_audit"])
    citations = [{"request_id":r["request_id"],"study_id":r["study_id"],"entry_id":r["entry_id"],
                  "arm":r["arm"],"target_title":r["title"],**c} for r in rows for c in r["citation_audit"]]
    write("Citation_Audit.csv",citations,["request_id","study_id","entry_id","arm","target_title",
          "template_id","citation_index","source","chunk_id","exact_quote","exact_match","applicability"])
    write("Protocol_Issues.csv",[r for r in rows if r["issues"] or r["protocol_repaired"]],
          ["request_id","original_record_status","original_error","original_selection_status",
           "original_selected_template","recommended_template","supported_template","protocol_repaired","issues"])
    return report, rows
