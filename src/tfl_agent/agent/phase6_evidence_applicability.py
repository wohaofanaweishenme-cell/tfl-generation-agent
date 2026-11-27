"""Phase 6.3.2: zero-call evidence applicability audit and conservative decision ablation.

Heuristic hints are triage, never verified semantic labels. Gold is evaluation-only.
No new retrieval, no library changes, no automatic elevation of uncertain decisions.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import zipfile
from collections import Counter
from pathlib import Path

from tfl_agent.agent.phase6_decision_replay import (
    ARCHIVE_SHA, load_frozen, replay_decision, _sha, _metrics)
from tfl_agent.agent.phase6_common import (
    cases, study_artifacts, verify_identity, extract_phase52, read)
from tfl_agent.agent.phase6_llm_pilot import ARMS
from tfl_agent.agent.scoped_specification import (
    STUDY_FIELDS, TARGET_FIELDS, literal_support)

REPLAY_SHA = "925d30bb565cd197dfa38f007742a06048c52ed4e95e13723bdd4328d625bad4"
REPLAY_NAME = "20261127T182431845414Z.zip"
HISTORICAL_SHA = "7418f09c9993b0ab505c791c36d7fadf9f60eb88966294a3ee102cbcafaafcbf"
VERSION = "6.3.2-v1"
APPLICABILITY = ("target_specific", "general_study_context", "topic_only",
                 "other_endpoint_or_output", "insufficient_context", "mixed")
DISCRIMINATION = ("supports_candidate_over_alternative", "does_not_distinguish",
                  "contradicts_candidate", "uncertain")
STOP = set("a an the of and or by for to in with from on at per during will be is are was were "
           "all each any summary summarized summarised analysis set population study patient patients "
           "subject subjects participant participants number percentage percentages percent frequency "
           "table figure listing data value values information results calculated described "
           "treatment arm groups group baseline safety total".split())


def tokens(text):
    # Lightweight normalization for triage only, not semantic similarity.
    return {x.rstrip("s") if len(x)>4 and x.endswith("s") else x
            for x in re.findall(r"[a-z][a-z0-9]+", str(text).lower()) if x not in STOP}


def triage(title, quote, section="", study_scope=None, source="sap"):
    """Hints do not determine applicability or gate decisions."""
    quote = quote if isinstance(quote,str) else ""
    t, q = tokens(title), tokens(quote)
    common = sorted(t & q)
    flags = []
    if source == "title":
        flags.append("title_evidence")
    else:
        if study_scope or re.search(r"\b(?:all safety analyses|unless otherwise stated|all analyses|general statistical)\b",quote,re.I):
            flags.append("possible_general_study_context")
        if re.search(r"\b(?:listing of|will be listed|displayed graphically|plot of|curves? will be produced)\b",quote,re.I):
            flags.append("possible_other_output")
        if common:
            flags.append("lexical_target_anchor")
        else:
            flags.append("no_lexical_target_anchor")
        if re.search(r"\b(?:confidence interval|CI|odds ratio|hazard ratio|by visit|SOC|PT|system organ class|preferred term|severity|categories|mean|median|frequency|frequencies|percentages?)\b",quote,re.I):
            flags.append("possible_structural_or_statistical_cue")
    return {"anchor_overlap":common,"triage_flags":flags,
            "applicability_label":"unreviewed","discrimination_label":"unreviewed"}


def context_window(text, quote, radius=350):
    i = text.find(quote) if isinstance(quote,str) and quote.strip() else -1
    if i<0:
        return {"quote_start":None,"quote_occurrences":0,"context_before":"","context_after":""}
    j=i+len(quote)
    return {"quote_start":i,"quote_occurrences":text.count(quote),
            "context_before":text[max(0,i-radius):i],"context_after":text[j:j+radius]}


def audit_pilot(requests, records, replay_rows):
    by_id={r["request_id"]:r for r in replay_rows}
    out=[]
    for req in requests:
        rid=req["request_id"]; p=req["payload"]; d=by_id[rid]
        raw=json.loads(records[rid]["raw_response"])
        assessments={a["template_id"]:a for a in raw["candidate_assessments"]}
        passages={c["chunk_id"]:c for c in p["sap_evidence"]}
        for c in d["citation_audit"]:
            src=c["source"]; quote=c["exact_quote"]; tid=c["template_id"]
            passage=passages[c["chunk_id"]] if src=="sap" else {}
            txt=passage["text"] if src=="sap" else p["target"]["title"]
            exact=bool(quote and quote in txt)
            if exact!=c["exact_match"]:
                raise ValueError("Citation replay mismatch")
            a=assessments[tid]
            out.append({"evidence_id":f'{rid}::{tid}::{c["citation_index"]}',
                        "request_id":rid,"study_id":req["study_id"],"entry_id":req["entry_id"],
                        "arm":req["arm"],"title":p["target"]["title"],"template_id":tid,
                        "is_top_candidate":tid==d["recommended_template"],
                        "candidate_compatibility":a["compatibility"],"candidate_reason":a["reason"],
                        "selection_reason":raw["reason"],"source":src,"chunk_id":c["chunk_id"],
                        "section":passage.get("section"),"pages":passage.get("pages"),
                        "exact_quote":quote,"exact_match":exact,**context_window(txt,quote),
                        **triage(p["target"]["title"],quote,passage.get("section"),source=src)})
    if len({r["evidence_id"] for r in out})!=len(out):
        raise ValueError("Duplicate citation identity")
    return out


def load_replay(path, requests, records):
    if _sha(path)!=REPLAY_SHA:
        raise ValueError("Phase 6.3.1 frozen archive hash mismatch")
    with zipfile.ZipFile(path) as z:
        rows=json.loads(z.read("Replayed_Decisions.json"))
        summary=json.loads(z.read("Summary.json"))
    idx={r["request_id"]:r for r in rows}
    if len(rows)!=18 or set(idx)!={r["request_id"] for r in requests}:
        raise ValueError("Replay identity mismatch")
    if summary["new_llm_calls"]!=0 or summary["source_archive_sha256"]!=ARCHIVE_SHA:
        raise ValueError("Replay lineage mismatch")
    for req in requests:
        rid=req["request_id"]; row=idx[rid]
        if row["fingerprint"]!=req["fingerprint"] or row["title"]!=req["payload"]["target"]["title"]:
            raise ValueError("Replay request mismatch")
        d=replay_decision(json.loads(records[rid]["raw_response"]),req["payload"])
        if any(row[k]!=v for k,v in d.items()):
            raise ValueError("Replay protocol drift")
        if row["generation_authorized"] or row["clinical_confirmation"]:
            raise ValueError("Unsafe source decision")
    return rows


def audit_historical(root):
    """Inventory every recorded initial/completion response, including study calls.
    Preserve raw rejected claims and old statuses, do not silently accept them.
    """
    manifest=cases(root)
    studies=sorted({c["study_id"] for c in manifest})
    out=[]; calls=[]
    for study in studies:
        store,_,parts,specs,_=study_artifacts(root,study)
        for case in (c for c in manifest if c["study_id"]==study):
            verify_identity(case,parts[case["entry_id"]],specs[case["entry_id"]])
        folder=Path(root)/"Studies"/study
        audits=read(folder/"TFL_Extraction_Audit.json")
        if {a["target"]["tfl_id"] for a in audits}!=set(specs) or len(audits)!=len(specs):
            raise ValueError("Historical target audit identity mismatch")
        scopes=[("study",None,read(folder/"Study_Extraction_Audit.json"),
                 read(folder/"Study_Settings.json"))]
        for a in audits:
            eid=a["target"]["tfl_id"]; spec=specs[eid]
            if any(a["target"].get(k)!=spec["identity"].get(k) for k in ("tfl_id","title","output_type")):
                raise ValueError("Historical audit/spec identity mismatch")
            scopes.append((eid,a["target"],a,spec))
        for eid,target,a,spec in scopes:
            title=target["title"] if target else ""
            old={}
            for status,key in (("accepted","claims"),("needs_review","review_claims")):
                for c in spec[key]:
                    ck=(c["field"],c["value"],c["chunk_id"],c["exact_quote"])
                    old.setdefault(ck,[]).append((status,c.get("checks",{}).get("scope_flags",[])))
            for stage in ("initial","completion"):
                raw=a.get(stage+"_response")
                if stage=="completion" and bool(raw is not None)!=bool(a["completion_attempted"]):
                    raise ValueError("Completion response count mismatch")
                if raw is None:
                    if stage=="initial": raise ValueError("Missing initial response")
                    continue
                ids=set(a[stage+"_evidence_ids"])
                if not ids<=set(store.chunks):
                    raise ValueError("Unknown historical evidence ID")
                claims=raw.get("claims") if isinstance(raw,dict) else None
                if not isinstance(claims,list):
                    raise ValueError("Malformed historical response")
                call_id=f"{study}::{eid}::{stage}"
                calls.append({"call_id":call_id,"study_id":study,"entry_id":eid,
                              "stage":stage,"claim_count":len(claims),"evidence_count":len(ids)})
                allowed=set(STUDY_FIELDS if target is None else TARGET_FIELDS)
                if stage=="completion": allowed &= set(a["missing_before"])
                for i,c in enumerate(claims):
                    raw_claim=c
                    c=c if isinstance(c,dict) else {}
                    f,v,cid,q=(c.get(k) for k in ("field","value","chunk_id","quote"))
                    wellformed=all(isinstance(x,str) and x.strip() for x in (f,v,cid,q))
                    eligible=wellformed and cid in ids
                    chunk=store.chunks.get(cid,{}) if isinstance(cid,str) else {}
                    exact=bool(eligible and store.locate(cid,q))
                    literal=bool(exact and literal_support(v,q))
                    key=(f,v,cid,q) if wellformed else None
                    prev=old.get(key,[])
                    out.append({"evidence_id":f"{call_id}::{i}","call_id":call_id,
                                "study_id":study,"entry_id":eid,"stage":stage,"title":title,
                                "output_type":target.get("output_type") if target else "study",
                                "field":f,"value":v,"chunk_id":cid,"exact_quote":q,
                                "raw_claim":raw_claim,"available_in_call":bool(eligible),
                                "field_allowed":bool(isinstance(f,str) and f in allowed),
                                "exact_match":exact,"literal_support":literal,
                                "source_spans":store.locate(cid,q) if exact else [],
                                "section":chunk.get("section"),"pages":chunk.get("pages"),
                                "study_scope":chunk.get("study_scope"),"topic_scope":chunk.get("topic_scope"),
                                "historical_status_matches":prev,
                                "historical_status_note":"Matched by content across stages; duplicates may share status.",
                                **context_window(chunk.get("text",""),q),
                                **triage(title,q or "",chunk.get("section"),chunk.get("study_scope"))})
    if len(calls)!=44 or len({c["call_id"] for c in calls})!=44:
        raise ValueError(f"Expected 44 recorded historical extraction responses, got {len(calls)}")
    return calls,out


def guarded_decision(title, sap):
    """Zero-call policy ablation, NOT an applicability classifier.

    Without independently established discriminating evidence, do not let SAP
    override a title recommendation or elevate an uncertain title to supported.
    An explicit SAP abstention or invalid response also blocks support.
    No evaluation labels or lexical hints are consulted.
    """
    a=title["recommended_template"]; b=sap["recommended_template"]
    rec=a if title["protocol_valid"] and title["decision_status"]!="no_compatible_template" else None
    if not sap["protocol_valid"] or not title["protocol_valid"]:
        status="protocol_invalid"
    elif sap["decision_status"]=="no_compatible_template" or title["decision_status"]=="no_compatible_template":
        status="explicit_abstention"
    elif a!=b:
        status="unverified_override_blocked"
    elif title["supported_template"] is None and sap["supported_template"] is not None:
        status="unverified_support_elevation_blocked"
    elif a is not None and title["supported_template"]==a and sap["supported_template"]==a:
        status="agreement_preserved"
    else:
        status="uncertainty_preserved"
    return {"guarded_recommendation":rec,
            "guarded_supported_template":a if status=="agreement_preserved" else None,
            "guarded_supported_preset":None,
            "decision_policy":status,"semantic_applicability_verified":False,
            "generation_authorized":False,"clinical_confirmation":False}


def compare_decisions(rows):
    by={(r["study_id"],r["entry_id"],r["arm"]):r for r in rows}
    out=[]
    for a in rows:
        if a["arm"]!=ARMS[0]: continue
        for arm in ARMS[1:]:
            b=by[a["study_id"],a["entry_id"],arm]
            if a["title"]!=b["title"] or a["expected"]!=b["expected"]:
                raise ValueError("Paired identity mismatch")
            # Gate sees inference fields only.
            keep=("recommended_template","supported_template","protocol_valid","decision_status")
            d=guarded_decision({k:a[k] for k in keep},{k:b[k] for k in keep})
            out.append({"study_id":a["study_id"],"entry_id":a["entry_id"],"title":a["title"],
                        "arm":arm,"expected":a["expected"],"title_recommendation":a["recommended_template"],
                        "title_supported_template":a["supported_template"],
                        "sap_recommendation":b["recommended_template"],"sap_supported_template":b["supported_template"],
                        "sap_request_id":b["request_id"],**d})
    return out


def _write(out,name,rows):
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with (out/name).open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in r.items()})


def run_applicability(pilot_zip,replay_zip,historical_zip,cache_dir,out):
    if _sha(historical_zip)!=HISTORICAL_SHA:
        raise ValueError("Historical Phase 5.2 archive hash mismatch")
    requests,records,labels,_=load_frozen(pilot_zip)
    rows=load_replay(replay_zip,requests,records)
    for r in rows:
        if r["expected"]!=labels[r["study_id"],r["entry_id"]]["expected"]:
            raise ValueError("Replay evaluation label mismatch")
    pilot=audit_pilot(requests,records,rows)
    root=extract_phase52(historical_zip,cache_dir)
    calls,claims=audit_historical(root)
    pairs=compare_decisions(rows)
    metrics={}
    for arm in ARMS[1:]:
        sub=[r for r in pairs if r["arm"]==arm]
        metrics[arm]={k:_metrics(sub,k) for k in (
            "title_recommendation","title_supported_template","sap_recommendation",
            "sap_supported_template","guarded_recommendation","guarded_supported_template")}
        metrics[arm]["gate_actions"]=dict(Counter(r["decision_policy"] for r in sub))
    report={"version":VERSION,"new_llm_calls":0,"pilot_responses":len(rows),
            "historical_responses":len(calls),"historical_claim_occurrences":len(claims),
            "pilot_citations":len(pilot),"pilot_sap_citations":sum(r["source"]=="sap" for r in pilot),
            "pilot_exact_matches":sum(r["exact_match"] for r in pilot),
            "historical_exact_matches":sum(r["exact_match"] for r in claims),
            "historical_literal_matches":sum(r["literal_support"] for r in claims),
            "independent_applicability_labels":0,"independent_discrimination_labels":0,
            "pilot_hint_counts":dict(Counter(f for r in pilot for f in r["triage_flags"])),
            "historical_hint_counts":dict(Counter(f for r in claims for f in r["triage_flags"])),
            "metrics":metrics,"generation_authorized":False,"clinical_confirmation":False,
            "source_sha256":{"pilot":ARCHIVE_SHA,"replay":REPLAY_SHA,"historical":HISTORICAL_SHA},
            "caveats":["Six development cases, no held-out performance claim.",
                       "Guarded recommendation defaults to title; the ablation cannot demonstrate semantic classification or improved ranking.",
                       "Gate deliberately cannot allow a beneficial SAP override yet; measure this in a future approved pilot.",
                       "Exact quotes and lexical overlap are not proof of applicability.",
                       "Historical claim occurrences include duplicates and rejected claims; not independent observations.",
                       "No preset accuracy labels; guarded policy does not select a preset."]}
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    _write(out,"Pilot_Citation_Applicability.csv",pilot)
    _write(out,"Historical_Claim_Applicability.csv",claims)
    _write(out,"Historical_Response_Inventory.csv",calls)
    _write(out,"Guarded_Decisions.csv",pairs)
    # Review queue excludes gold labels; annotations are for evaluation, not runtime approval.
    queue=[r for r in pilot if r["source"]=="sap"]+claims
    _write(out,"Applicability_Review_Queue.csv",queue)
    (out/"Applicability_Taxonomy.json").write_text(json.dumps({
        "applicability_labels":APPLICABILITY,"discrimination_labels":DISCRIMINATION,
        "unit":"one cited passage/claim for a specified target and proposed use",
        "rule":"Review full context and competing structure; mixed or insufficient evidence stays uncertain.",
        "review_is_offline_evaluation_only":True},indent=2)+"\n")
    (out/"Summary.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    return report,pairs
