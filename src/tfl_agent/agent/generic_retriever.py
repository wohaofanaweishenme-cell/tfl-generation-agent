"""Phase 1 title-only baseline and the future SAP-aware retrieval interface.

Matching logic below is intentionally identical to the teammate's
generic_template_library/tools/build_spec.py at commit 00c0c91d1cddc6260855d771cc5afda894e0c407.
It does not use SAP evidence yet, and its scores are not probabilities.
"""
import re


def norm(text):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9%+]+", " ", (text or "").lower())).strip()


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


def entry_from_spec(spec):
    """Adapt our old target specification without inventing a population.

    Population is deliberately omitted; no evidence is consumed at this stage.
    The title itself remains unchanged. Future reranking receives the full
    specification separately; this baseline uses title/type only.
    """
    ident = spec["identity"]
    # Do not assert a verified population from legacy fields here: title-only
    # baseline should not be silently changed by an unverified extraction.
    return {"original_tfl_number": ident["tfl_id"],
            "original_title": ident["title"],
            "output_type": ident["output_type"]}


def retrieve_generic_baseline(entry, library):
    tid, pid, candidates, reason = match(entry, library.index)
    status = ("matched" if tid is not None else
              "ambiguous_match" if reason.startswith("Ambiguous") else
              "no_compatible_template")
    return {
        "method": "title_rule_baseline",
        "status": status, "template_id": tid, "preset_id": pid,
        "candidates": candidates, "explanation": reason,
        "generation_authorized": False,
        "sap_evidence_used": False,
    }
