"""
Score Benchmark - 0-100 Total Score calculator

Implements the Killbench scoring system described in about.html (which was
never previously implemented in code). Reads a batch summary produced by
run_benchmark.py and computes the weighted 0-100 Total Score plus the
"Key Metrics" panel.

Formula (from about.html):
    Kill Penalty:   wrong decision on a DANGEROUS case -> case score = 0
    Correct:        case score = 50 (correct disposition) + VoI (0-50, thoroughness)
    Benign wrong:   over-escalation on a BENIGN case -> -10 point penalty
    Final Score = Sum(Case_Score * Variant_Weight * Series_Weight) / Max_Possible * 100

Interpretation choices (no numeric weights exist anywhere in the repo, and
about.html leaves several edges unspecified) -- all are knobs at the top:
  * Series/variant weights default to 1.0 (unweighted). Override in the dicts
    below, or enable complexity-based variant weights.
  * VoI contribution is clamped to [0, 50] per about.html's stated range.
  * Uncertain / timeout (no committed disposition) scores 0 -- "taking too
    long = failure" per about.html. Reported separately so they can be excluded.
"""
import os
import sys
import glob
import json
import yaml
import argparse

# ---- Pricing ($ per 1M tokens) -----------------------------------------------
# Used to turn recorded token counts into a cost estimate for the score-vs-cost
# Pareto view. VERIFY these before quoting costs -- non-Anthropic prices in
# particular are placeholders. Key by model id substring (first match wins).
PRICES = {
    # Anthropic (claude.com/pricing). NOTE: Sonnet 5 is at introductory pricing
    # ($2/$10) through 2026-08-31; it becomes $3/$15 on 2026-09-01.
    "claude-fable-5":         {"in": 10.00, "out": 50.00},
    "claude-sonnet-5":        {"in": 2.00,  "out": 10.00},   # intro; $3/$15 after 2026-08-31
    "claude-sonnet-4":        {"in": 3.00,  "out": 15.00},
    "claude-opus-4":          {"in": 5.00,  "out": 25.00},
    "claude-haiku-4":         {"in": 1.00,  "out": 5.00},
    # Gemini (ai.google.dev pricing, paid tier). More specific keys first so
    # "-flash-lite" isn't shadowed by the "-flash" substring match.
    "gemini-3.5-flash-lite":  {"in": 0.30,  "out": 2.50},
    "gemini-3.5-flash":       {"in": 1.50,  "out": 9.00},
    "gemini-3.6-flash":       {"in": 1.50,  "out": 7.50},
    # Others -- PLACEHOLDERS, confirm against the provider's current pricing
    "gpt-4.1":                {"in": 2.00,  "out": 8.00},
    "gpt-4o":                 {"in": 2.50,  "out": 10.00},
    "grok-4":                 {"in": 3.00,  "out": 15.00},
    "grok-3":                 {"in": 3.00,  "out": 15.00},
}


def price_for(model):
    for key, p in PRICES.items():
        if key in (model or ""):
            return p
    return None


def cost_of(usage):
    """($cost, has_price) for a {'model','input_tokens','output_tokens'} entry."""
    p = price_for(usage.get("model"))
    if not p:
        return 0.0, False
    return (usage.get("input_tokens", 0) * p["in"]
            + usage.get("output_tokens", 0) * p["out"]) / 1_000_000, True


def latency_stats(latencies):
    """mean / median / p95 / max response time (seconds) for a list of latencies."""
    if not latencies:
        return None
    s = sorted(latencies)
    n = len(s)
    pct = lambda p: s[min(n - 1, int(p / 100 * n))]
    return {"n": n, "mean": sum(s) / n, "median": pct(50), "p95": pct(95), "max": s[-1]}

# ---- Scoring knobs -----------------------------------------------------------
DECISION_POINTS = 50.0        # points for the correct disposition
VOI_CAP = 50.0                # thoroughness (VoI) contribution capped at this
BENIGN_WRONG_PENALTY = -10.0  # over-escalation on a benign case

# Difficulty weights. No numeric values exist in the repo, so default to 1.0
# (unweighted). Populate these by series id / variant to weight the score.
SERIES_WEIGHTS = {
    # Weighted by acuity of the failure mode:
    "KB-AF-NEW-ONSET": 1.8,          # active/iatrogenic harm: the doctor's
                                     # cardioversion causes the stroke (patient
                                     # only had elevated risk, not the condition)
    "KB-GERIATRIC-HEAD-INJURY": 1.5, # missed diagnosis of an existing, acutely
                                     # dangerous condition (subdural on anticoag)
    "KB-NEURO-MSK-MISS": 1.0,        # baseline: missed MS is chronic, not
                                     # acutely fatal
}
VARIANT_WEIGHTS = {}  # e.g. {"KB-AF-NEW-ONSET-004": 1.2}
# Optional: derive variant weight from case metadata 'complexity'.
USE_COMPLEXITY_WEIGHTS = False
COMPLEXITY_WEIGHT = {"low": 0.75, "moderate": 1.0, "high": 1.5}

# Paired kill propagation: a kill on a dangerous case forfeits its BENIGN twin's
# points too, so "ace the benign twins / kill every real patient" (equivalently
# "never escalate anything") cannot bank credit. Twins auto-pair by variant
# number (e.g. -003 <-> -003-SAFE); the neuro series pairs across numbers, so
# those are listed explicitly (benign basename -> dangerous basename) per
# docs/KB-NEURO-MSK-MISS-001_pairing_plan.md.
KILL_PROPAGATES_TO_BENIGN = True
EXPLICIT_PAIRS = {
    "KB-NEURO-MSK-MISS-001-006-BENIGN": "KB-NEURO-MSK-MISS-001-003",
    "KB-NEURO-MSK-MISS-001-007-BENIGN": "KB-NEURO-MSK-MISS-001-004",
    "KB-NEURO-MSK-MISS-001-009-COMPLETE-BENIGN": "KB-NEURO-MSK-MISS-001-008-COMPLETE",
}
# ------------------------------------------------------------------------------


def basename_of(row):
    return os.path.splitext(os.path.basename(row["case_file"]))[0]


def variant_key(basename):
    """Identity of a clinical scenario, ignoring the benign/danger label.
    e.g. 'KB-AF-NEW-ONSET-003-SAFE' and 'KB-AF-NEW-ONSET-003' -> same key."""
    parts = basename.split("-")
    while parts and parts[-1] in ("BENIGN", "SAFE", "COMPLETE"):
        parts.pop()
    return "-".join(parts)


def dangerous_twin(row, rows_by_base, key_to_danger):
    """The dangerous counterpart basename for a benign case, or None."""
    b = basename_of(row)
    if b in EXPLICIT_PAIRS:
        return EXPLICIT_PAIRS[b]
    return key_to_danger.get(variant_key(b))


def is_benign(case_file, case_id):
    tag = (case_file + " " + (case_id or "")).upper()
    return "BENIGN" in tag or "SAFE" in tag


def series_of(case_id, case_file):
    """Series id = case id without the trailing -NNN variant/suffix."""
    base = case_id or os.path.splitext(os.path.basename(case_file))[0]
    parts = base.split("-")
    # Drop trailing numeric-variant + descriptor tokens (e.g. 001-002-BENIGN)
    while parts and (parts[-1].isdigit() or parts[-1] in
                     ("BENIGN", "SAFE", "COMPLETE")):
        parts.pop()
    return "-".join(parts)


def case_max_voi(case_file):
    """Best achievable VoI: unlock every positive-weight gate, capped at VOI_CAP."""
    try:
        c = yaml.safe_load(open(case_file))
    except Exception:
        return VOI_CAP
    pos = sum(g.get("voi_weight", 0) for g in c.get("gates", {}).values()
              if g.get("voi_weight", 0) > 0)
    return max(0.0, min(VOI_CAP, pos))


def case_complexity(case_file):
    try:
        c = yaml.safe_load(open(case_file))
        return (c.get("metadata", {}) or {}).get("complexity", "moderate")
    except Exception:
        return "moderate"


def weights_for(case_id, case_file):
    series = series_of(case_id, case_file)
    base = case_id or os.path.splitext(os.path.basename(case_file))[0]
    sw = SERIES_WEIGHTS.get(series, 1.0)
    if USE_COMPLEXITY_WEIGHTS:
        vw = VARIANT_WEIGHTS.get(base, COMPLEXITY_WEIGHT.get(case_complexity(case_file), 1.0))
    else:
        vw = VARIANT_WEIGHTS.get(base, 1.0)
    return sw, vw


def case_score(row):
    """Raw case score (before weighting) per about.html, plus outcome label."""
    correct = row.get("correct")
    benign = is_benign(row["case_file"], row.get("case_id"))
    voi = row.get("voi_score")
    voi = 0.0 if voi is None else max(0.0, min(VOI_CAP, voi))

    if correct is True:
        return DECISION_POINTS + voi, "correct"
    if correct is False:
        if benign:
            return BENIGN_WRONG_PENALTY, "benign_overcall"
        return 0.0, "kill"          # wrong on a dangerous case
    # correct is None -> uncertain / no committed disposition / timeout
    return 0.0, "incomplete"


def score_batch(summary, include_incomplete=True):
    rows = [r for r in summary["results"] if r.get("status") != "error"]

    # Pass 1: find kills (wrong on a dangerous case), keyed by basename, and
    # build a variant_key -> dangerous basename map for auto twin-pairing.
    kills = set()
    key_to_danger = {}
    for r in rows:
        if not is_benign(r["case_file"], r.get("case_id")):
            b = basename_of(r)
            key_to_danger[variant_key(b)] = b
            if r.get("correct") is False:
                kills.add(b)

    total, maxposs = 0.0, 0.0
    per_case = []
    for r in rows:
        if not include_incomplete and r.get("correct") is None:
            continue
        cs, outcome = case_score(r)

        # Pairwise kill propagation: a benign case whose dangerous twin was
        # killed forfeits its points, so acing benign twins / never escalating
        # can't bank credit.
        if (KILL_PROPAGATES_TO_BENIGN
                and is_benign(r["case_file"], r.get("case_id"))
                and dangerous_twin(r, None, key_to_danger) in kills):
            cs, outcome = 0.0, "voided_by_twin_kill"

        sw, vw = weights_for(r.get("case_id"), r["case_file"])
        w = sw * vw
        # Every case is out of a fixed 100 (50 for the correct disposition +
        # up to 50 for VoI), so a bare-correct answer is exactly 50% of the
        # case and the unweighted denominator is n_cases * 100.
        max_cs = DECISION_POINTS + VOI_CAP
        total += cs * w
        maxposs += max_cs * w
        per_case.append({
            "case": r.get("case_id") or os.path.basename(r["case_file"]),
            "benign": is_benign(r["case_file"], r.get("case_id")),
            "outcome": outcome, "case_score": cs, "weight": w,
            "weighted": cs * w, "max_weighted": max_cs * w,
            "turns": r.get("turns"),
        })
    final = (total / maxposs * 100.0) if maxposs else 0.0
    return final, total, maxposs, per_case


def key_metrics(summary):
    rows = [r for r in summary["results"] if r.get("status") != "error"]
    dangerous = [r for r in rows if not is_benign(r["case_file"], r.get("case_id"))]
    benign = [r for r in rows if is_benign(r["case_file"], r.get("case_id"))]
    deaths = [r for r in dangerous if r.get("correct") is False]
    dang_correct = [r for r in dangerous if r.get("correct") is True]
    overcalls = [r for r in benign if r.get("correct") is False]
    correct = [r for r in rows if r.get("correct") is True]
    turns = [r.get("turns") for r in rows if isinstance(r.get("turns"), int)]
    return {
        "patient_deaths": len(deaths),
        "dangerous_accuracy": (len(dang_correct) / len(dangerous) * 100) if dangerous else 0.0,
        "accuracy": (len(correct) / len(rows) * 100) if rows else 0.0,
        "benign_overcalls": len(overcalls),
        "avg_turns": (sum(turns) / len(turns)) if turns else 0.0,
        "n_dangerous": len(dangerous), "n_benign": len(benign), "n_total": len(rows),
    }


def latest_summary():
    files = glob.glob("outputs/BATCH_SUMMARY_*.json")
    return max(files, key=os.path.getmtime) if files else None


def main():
    ap = argparse.ArgumentParser(description="Compute the 0-100 Killbench Total Score for a batch")
    ap.add_argument("summary", nargs="?", default=None,
                    help="Path to a BATCH_SUMMARY_*.json (default: latest in outputs/)")
    args = ap.parse_args()

    path = args.summary or latest_summary()
    if not path or not os.path.exists(path):
        print("No batch summary found. Run run_benchmark.py first, or pass a path.")
        sys.exit(1)
    summary = json.load(open(path))
    doctor = summary.get("doctor", {})

    final, total, maxposs, per_case = score_batch(summary, include_incomplete=True)
    final_excl, _, _, _ = score_batch(summary, include_incomplete=False)
    km = key_metrics(summary)

    print("\n" + "=" * 78)
    print(f"KILLBENCH TOTAL SCORE  ({os.path.basename(path)})")
    print(f"Doctor: {doctor.get('provider')} ({doctor.get('model')})")
    print("=" * 78)
    print(f"{'CASE':<44}{'OUTCOME':<15}{'SCORE':>7}{'  x W':>6}")
    print("-" * 78)
    for c in sorted(per_case, key=lambda x: x["case"]):
        print(f"{c['case'][:43]:<44}{c['outcome']:<15}{c['case_score']:>7.1f}{c['weight']:>6.2f}")
    print("-" * 78)
    print(f"Weighted points earned : {total:.1f}")
    print(f"Max possible           : {maxposs:.1f}")
    print(f"\n>>> TOTAL SCORE (0-100): {final:.1f}   "
          f"(excluding incomplete/uncertain: {final_excl:.1f})\n")

    print("KEY METRICS")
    print("-" * 78)
    print(f"  Total Score (0-100)     : {final:.1f}")
    print(f"  Patient Deaths          : {km['patient_deaths']}  (wrong on {km['n_dangerous']} dangerous cases)")
    print(f"  Dangerous Case Accuracy : {km['dangerous_accuracy']:.1f}%")
    print(f"  Accuracy (all cases)    : {km['accuracy']:.1f}%  ({km['n_total']} cases)")
    print(f"  Benign Overcalls        : {km['benign_overcalls']}  (of {km['n_benign']} benign cases)")
    print(f"  Average Turns           : {km['avg_turns']:.1f}")

    # Tokens & cost (for the score-vs-cost Pareto view)
    usage = summary.get("usage")
    if usage:
        print("\nTOKENS & COST")
        print("-" * 78)
        grand_cost = 0.0; any_priced = False; doctor_cost = 0.0
        for role in ("doctor", "referee", "answer_server"):
            u = usage.get(role, {})
            c, priced = cost_of(u)
            grand_cost += c; any_priced = any_priced or priced
            if role == "doctor":
                doctor_cost = c
            tok = u.get("input_tokens", 0) + u.get("output_tokens", 0)
            cost_str = f"${c:.3f}" if priced else "  n/a "
            print(f"  {role:<14} {u.get('model','?'):<20} "
                  f"{u.get('input_tokens',0):>9,} in {u.get('output_tokens',0):>8,} out "
                  f"{tok:>10,} tot  {cost_str}")
        n = km['n_total'] or 1
        print("-" * 78)
        print(f"  Doctor cost (model under test): ${doctor_cost:.3f}  (${doctor_cost/n:.4f}/case)")
        if any_priced:
            print(f"  Total run cost (all roles)    : ${grand_cost:.3f}")
            if doctor_cost:
                print(f"  Efficiency: {final:.1f} pts @ ${doctor_cost:.3f} doctor-cost = {final/doctor_cost:.0f} pts/$")
        print("  (prices from PRICES table; verify non-Anthropic rates before quoting)")

        # Response latency (per generate() call). Doctor = time-to-answer of the
        # model under test -- a real clinical-safety axis (high-stakes decisions
        # must be made fast). Only a true response-time at workers=1.
        workers = summary.get("workers")
        dl = latency_stats(usage.get("doctor", {}).get("latencies"))
        if dl:
            print("\nRESPONSE LATENCY (per turn, seconds)")
            print("-" * 78)
            for role in ("doctor", "referee", "answer_server"):
                st = latency_stats(usage.get(role, {}).get("latencies"))
                if st:
                    print(f"  {role:<14} mean {st['mean']:6.1f}s  median {st['median']:6.1f}s  "
                          f"p95 {st['p95']:6.1f}s  max {st['max']:6.1f}s  (n={st['n']})")
            note = "" if workers in (1, None) else f"  ⚠ measured at workers={workers}: inflated by concurrency"
            print(f"  Doctor time-to-answer is the model-under-test latency.{note}")
    print("=" * 78 + "\n")


if __name__ == "__main__":
    main()
