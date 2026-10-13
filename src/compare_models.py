"""
Compare Models - cross-batch aggregator

score_benchmark.py scores ONE batch. This rolls many batches up into the
score x cost x turns x latency comparison, grouping by (doctor model, effort)
and reporting mean +/- spread across repeats.

Usage:
    python src/compare_models.py --dir outputs --csv out.csv --md out.md
"""
import os
import csv
import glob
import json
import argparse
import math
import statistics as stats

import score_benchmark as sb


def load_summaries(pattern_dir, since=None):
    files = sorted(glob.glob(os.path.join(pattern_dir, "BATCH_SUMMARY_*.json")))
    out = []
    for f in files:
        try:
            with open(f) as fh:
                s = json.load(fh)
        except (json.JSONDecodeError, OSError):
            continue
        if not s.get("results"):
            continue
        # Skip batches that failed wholesale (e.g. an exhausted API key) -- they
        # carry no signal and would drag a model's mean down to zero.
        if all(r.get("status") == "error" for r in s["results"]):
            continue
        if since and s.get("batch_stamp", "") < since:
            continue
        out.append((f, s))
    return out


def role_cost(summary, role):
    u = summary.get("usage", {}).get(role)
    if not u:
        return 0.0, False
    return sb.cost_of(u)


def summarise_one(summary):
    """Collapse a single batch into the row-level facts we aggregate."""
    score, _, _, per_case = sb.score_batch(summary, include_incomplete=True)
    # Per-case scores, normalised to 0-100 of what that case was worth. Kept so
    # models can be compared case-by-case rather than batch-mean vs batch-mean:
    # every model runs the identical suite, so pairing on the case removes
    # case-difficulty variance and is far more powerful at this sample size.
    case_scores = {p["case_file"]: (p["weighted"] / p["max_weighted"] * 100)
                   for p in per_case if p.get("max_weighted")}
    km = sb.key_metrics(summary)
    doctor_cost, priced = role_cost(summary, "doctor")
    overhead = sum(role_cost(summary, r)[0] for r in ("referee", "answer_server"))
    u = summary.get("usage", {}).get("doctor", {}) or {}
    lat = sb.latency_stats(u.get("latencies") or [])
    # How much of the available information did it gather on the cases it got
    # right? A correct call with no workup still scores the full decision points,
    # so this is what separates reasoning from a confident guess.
    fracs = []
    for r in summary["results"]:
        if r.get("correct") is not True:
            continue
        mx = sb.case_max_voi(r["case_file"])
        if mx:
            fracs.append(min(1.0, (r.get("voi_score") or 0) / mx))
    # Kill and overcall rates are kept separate from their counts because the
    # suite is a 12/12 split, which hugely over-represents dangerous cases. To
    # reason about real deployment the two rates have to be re-weighted onto a
    # realistic prevalence -- see prevalence_projection().
    dang = [r for r in summary["results"]
            if r.get("status") != "error" and not sb.is_benign(r["case_file"], r.get("case_id"))]
    ben = [r for r in summary["results"]
           if r.get("status") != "error" and sb.is_benign(r["case_file"], r.get("case_id"))]
    kill_rate = (sum(1 for r in dang if r.get("correct") is False) / len(dang)) if dang else 0.0
    over_rate = (sum(1 for r in ben if r.get("correct") is False) / len(ben)) if ben else 0.0
    return {
        "score": score,
        "case_scores": case_scores,
        "kill_rate": kill_rate,
        "over_rate": over_rate,
        "cost": doctor_cost,
        "overhead": overhead,
        "priced": priced,
        "latency": lat,
        # Latency is wall-clock per call, so it only means "time to answer" when
        # cases ran one at a time; concurrent batches inflate it.
        "latency_valid": (summary.get("workers") or 1) == 1,
        "in_tok": u.get("input_tokens", 0),
        "out_tok": u.get("output_tokens", 0),
        "think_tok": u.get("thinking_tokens", 0),
        "cached_tok": u.get("cached_input_tokens", 0),
        "voi_frac": (sum(fracs) / len(fracs)) if fracs else None,
        "n_cases": len(summary.get("results", [])),
        "n_error": sum(1 for r in summary["results"] if r.get("status") == "error"),
        **km,
    }


def aggregate(summaries):
    groups = {}
    for path, s in summaries:
        model = (s.get("doctor") or {}).get("model", "?")
        effort = s.get("effort") or "default"
        groups.setdefault((model, effort), []).append((path, summarise_one(s)))

    rows = []
    for (model, effort), entries in sorted(groups.items()):
        runs = [e[1] for e in entries]
        scores = [r["score"] for r in runs]
        # Average cost only over runs we can actually price. Older batches
        # predate usage tracking; letting one of them into the mean would drag
        # the average toward zero, and marking the whole group "n/a" would throw
        # away good data.
        priced_runs = [r for r in runs if r["priced"]]
        costs = [r["cost"] for r in priced_runs] or [0.0]
        lat_runs = [r for r in runs if r["latency_valid"] and r["latency"]]
        cases = {}
        for r in runs:
            for c, v in r["case_scores"].items():
                cases.setdefault(c, []).append(v)
        rows.append({
            "model": model,
            "effort": effort,
            "cases": cases,
            "n_runs": len(runs),
            "score_mean": stats.mean(scores),
            "score_sd": stats.stdev(scores) if len(scores) > 1 else 0.0,
            "score_min": min(scores),
            "score_max": max(scores),
            "cost_mean": stats.mean(costs),
            "overhead_mean": stats.mean([r["overhead"] for r in priced_runs] or [0.0]),
            "priced": bool(priced_runs),
            "n_priced": len(priced_runs),
            "avg_turns": stats.mean([r["avg_turns"] for r in runs]),
            "deaths": stats.mean([r["patient_deaths"] for r in runs]),
            # In a safety-critical domain competence is judged by the worst
            # shift, not the average one, so the tail is reported alongside the
            # mean: most deaths and lowest dangerous-case accuracy across repeats.
            "deaths_worst": max(r["patient_deaths"] for r in runs),
            "dangerous_acc": stats.mean([r["dangerous_accuracy"] for r in runs]),
            "dangerous_acc_worst": min(r["dangerous_accuracy"] for r in runs),
            "score_worst": min(r["score"] for r in runs),
            # Fraction of the available information gathered on cases it got
            # right -- separates a justified answer from a lucky one.
            "voi_frac": stats.mean([r["voi_frac"] for r in runs if r["voi_frac"] is not None] or [0.0]),
            "kill_rate": stats.mean([r["kill_rate"] for r in runs]),
            "over_rate": stats.mean([r["over_rate"] for r in runs]),
            # Presentation axes, all 0-100 and all "higher is better", so they can
            # sit on one radar. Safety and specificity are the clinical pair:
            # sensitivity on the cases that kill, specificity on the ones that
            # don't. Time and cost stay in real units -- normalising money and
            # seconds hides the thing that makes them decision-relevant.
            "m_overall": stats.mean([r["score"] for r in runs]),
            "m_safety": (1 - stats.mean([r["kill_rate"] for r in runs])) * 100,
            "m_specificity": (1 - stats.mean([r["over_rate"] for r in runs])) * 100,
            "m_thoroughness": stats.mean(
                [r["voi_frac"] for r in runs if r["voi_frac"] is not None] or [0.0]) * 100,
            "overcalls": stats.mean([r["benign_overcalls"] for r in runs]),
            "accuracy": stats.mean([r["accuracy"] for r in runs]),
            "errors": sum(r["n_error"] for r in runs),
            "in_tok": stats.mean([r["in_tok"] for r in runs]),
            "out_tok": stats.mean([r["out_tok"] for r in runs]),
            "think_tok": stats.mean([r["think_tok"] for r in runs]),
            # Latency only from workers=1 batches; None means "not measured cleanly".
            "lat_mean": stats.mean([r["latency"]["mean"] for r in lat_runs]) if lat_runs else None,
            "lat_median": stats.mean([r["latency"]["median"] for r in lat_runs]) if lat_runs else None,
            "lat_p95": stats.mean([r["latency"]["p95"] for r in lat_runs]) if lat_runs else None,
            "n_lat_runs": len(lat_runs),
        })
    # Turn count normalised across arms (0-100 of the most inquisitive model).
    # Deliberately NOT signed as good/bad: on this suite more questions tracked
    # better outcomes, but running to the turn cap is its own failure.
    tmax = max((r["avg_turns"] for r in rows), default=0) or 1
    for r in rows:
        r["m_turns"] = r["avg_turns"] / tmax * 100
    return rows


def paired_test(row_a, row_b):
    """Paired t-test on per-case mean scores (row_a - row_b).

    Both arms ran the same suite, so the pairing is on the case: this strips out
    "some cases are just harder" and leaves the model difference. Returns
    (mean_diff, se, t, p, n_cases), or None if there is nothing to compare.
    """
    ca, cb = row_a.get("cases") or {}, row_b.get("cases") or {}
    shared = sorted(set(ca) & set(cb))
    diffs = [stats.mean(ca[c]) - stats.mean(cb[c]) for c in shared if ca[c] and cb[c]]
    if len(diffs) < 3:
        return None
    n = len(diffs)
    m = stats.mean(diffs)
    sd = stats.stdev(diffs)
    if sd == 0:
        return (m, 0.0, float("inf") if m else 0.0, 0.0 if m else 1.0, n)
    se = sd / math.sqrt(n)
    t = m / se
    try:
        from scipy import stats as _sps
        p = 2 * (1 - _sps.t.cdf(abs(t), df=n - 1))
    except Exception:
        # Normal approximation is close enough at df>=20 for a reported p.
        p = math.erfc(abs(t) / math.sqrt(2))
    return (m, se, t, p, n)


def sig_label(p):
    if p is None:
        return "-"
    if p < 0.01:
        return "**p<0.01**"
    if p < 0.05:
        return "*p<0.05*"
    return f"n.s. (p={p:.2f})"


DEFAULT_PREVALENCE = 0.08


def confusion_at_prevalence(rows, n=1000, prevalence=DEFAULT_PREVALENCE):
    """Full 2x2 at a realistic case mix, plus the predictive values.

    Sensitivity and specificity are properties of the model and do not move with
    prevalence; PPV and NPV do, and at 8% dangerous they are what actually
    matters clinically. A model can look excellent on specificity and still
    generate mostly false alarms once the benign population outnumbers the
    dangerous one 11:1.

    "Correct on a dangerous case" stands in for a true positive and "correct on
    a benign case" for a true negative -- the disposition taxonomy is richer than
    escalate/don't, so correctness is the faithful operationalisation.
    """
    out = []
    n_dang = n * prevalence
    n_ben = n * (1 - prevalence)
    for r in rows:
        sens = 1 - r["kill_rate"]          # dangerous cases decided correctly
        spec = 1 - r["over_rate"]          # benign cases not escalated
        tp, fn = sens * n_dang, (1 - sens) * n_dang
        tn, fp = spec * n_ben, (1 - spec) * n_ben
        out.append({
            "model": r["model"], "effort": r["effort"],
            "sens": sens * 100, "spec": spec * 100,
            "tp": tp, "fn": fn, "tn": tn, "fp": fp,
            "ppv": (tp / (tp + fp) * 100) if (tp + fp) else 0.0,
            "npv": (tn / (tn + fn) * 100) if (tn + fn) else 0.0,
        })
    # Reference strategies: NPV is dominated by prevalence, so a model's NPV is
    # only meaningful against the trivial policies. Discharge-everything already
    # scores NPV = 1 - prevalence without looking at the patient.
    out.append({"model": "(discharge everything)", "effort": "-",
                "sens": 0.0, "spec": 100.0, "tp": 0.0, "fn": n_dang, "tn": n_ben, "fp": 0.0,
                "ppv": 0.0, "npv": n_ben / (n_ben + n_dang) * 100, "baseline": True})
    out.append({"model": "(escalate everything)", "effort": "-",
                "sens": 100.0, "spec": 0.0, "tp": n_dang, "fn": 0.0, "tn": 0.0, "fp": n_ben,
                "ppv": prevalence * 100, "npv": 0.0, "baseline": True})
    return sorted(out, key=lambda x: -x["npv"])


def prevalence_projection(rows, n=1000, prevalence=DEFAULT_PREVALENCE):
    """Re-weight kill and overcall rates onto a realistic case mix.

    The suite is half dangerous by construction; a real ED is not. Overcalls
    scale with the common population and kills with the rare one, so the
    benchmark's 12/12 split flatters models that buy safety with escalation.
    Every unnecessary admission also consumes capacity the next dangerous case
    needs -- a downstream cost this projection does NOT attempt to model.
    """
    out = []
    for r in rows:
        out.append({
            "model": r["model"], "effort": r["effort"],
            "kill_rate": r["kill_rate"], "over_rate": r["over_rate"],
            "deaths": r["kill_rate"] * n * prevalence,
            "admits": r["over_rate"] * n * (1 - prevalence),
        })
    return sorted(out, key=lambda x: x["deaths"])


def pareto_front(rows):
    """Models where nothing else is both cheaper AND better."""
    front = []
    for r in rows:
        if r["cost_mean"] <= 0:
            continue
        dominated = any(
            o is not r and o["cost_mean"] <= r["cost_mean"] and o["score_mean"] >= r["score_mean"]
            and (o["cost_mean"] < r["cost_mean"] or o["score_mean"] > r["score_mean"])
            for o in rows
        )
        if not dominated:
            front.append(r)
    return sorted(front, key=lambda r: r["cost_mean"])


def fmt(v, spec="{:.2f}", dash="-"):
    return dash if v is None else spec.format(v)


def write_csv(rows, path):
    if not rows:
        return
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def to_markdown(rows):
    L = []
    L.append("# killbench - frontier model comparison\n")
    L.append("| Model | Effort | Runs | Score | SD | $/suite | Turns | Latency s (med) | Deaths (mean/worst) | Dang.acc mean/worst % | Overcalls | Info gathered |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in sorted(rows, key=lambda x: -x["score_mean"]):
        price = f"${r['cost_mean']:.2f}" if r["priced"] else "n/a"
        lat = fmt(r["lat_median"], "{:.1f}")
        if r["n_lat_runs"] == 0:
            lat += " (concurrent)"
        L.append(
            f"| `{r['model']}` | {r['effort']} | {r['n_runs']} | "
            f"{r['score_mean']:.1f} | {r['score_sd']:.1f} | {price} | "
            f"{r['avg_turns']:.1f} | {lat} | {r['deaths']:.1f} / {r['deaths_worst']:.0f} | "
            f"{r['dangerous_acc']:.0f} / {r['dangerous_acc_worst']:.0f} | {r['overcalls']:.1f} | "
            f"{r['voi_frac']*100:.0f}% |"
        )
    L.append("\n## Worst run (tail risk)\n")
    L.append("Competence in a safety-critical domain is judged by the worst shift, "
             "not the average one. Deaths are out of 12 dangerous cases.\n")
    L.append("| Model | Effort | Deaths worst | Dang.acc worst | Score worst |")
    L.append("|---|---|---|---|---|")
    for r in sorted(rows, key=lambda x: (x["deaths_worst"], -x["dangerous_acc_worst"])):
        L.append(f"| `{r['model']}` | {r['effort']} | {r['deaths_worst']:.0f} | "
                 f"{r['dangerous_acc_worst']:.0f}% | {r['score_worst']:.1f} |")

    L.append("\n## Model profiles (0-100, higher is better)\n")
    L.append("Safety is sensitivity on the dangerous cases; specificity is the inverse of "
             "over-escalation on the benign twins. Time and cost stay in real units.\n")
    L.append("| Model | Effort | Overall | Safety | Specificity | Thoroughness | Turns (rel) | s/turn | $/suite |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for r in sorted(rows, key=lambda x: -x["m_overall"]):
        lat = "-" if r["lat_median"] is None else f"{r['lat_median']:.1f}"
        L.append(f"| `{r['model']}` | {r['effort']} | {r['m_overall']:.0f} | {r['m_safety']:.0f} | "
                 f"{r['m_specificity']:.0f} | {r['m_thoroughness']:.0f} | {r['m_turns']:.0f} | "
                 f"{lat} | ${r['cost_mean']:.2f} |")

    proj = prevalence_projection(rows)
    L.append(f"\n## Projected onto 1,000 ED presentations ({DEFAULT_PREVALENCE:.0%} dangerous)\n")
    L.append("The suite is half dangerous by construction; a real ED is not. Overcalls scale "
             "with the common population, kills with the rare one. Every unneeded admission "
             "also consumes capacity the next dangerous case needs - a cost not counted here.\n")
    L.append("| Model | Effort | Kill rate | Overcall rate | Deaths | Unneeded admits |")
    L.append("|---|---|---|---|---|---|")
    for p in proj:
        L.append(f"| `{p['model']}` | {p['effort']} | {p['kill_rate']*100:.0f}% | "
                 f"{p['over_rate']*100:.0f}% | {p['deaths']:.0f} | {p['admits']:.0f} |")

    cm2 = confusion_at_prevalence(rows)
    L.append(f"\n## Diagnostic performance at {DEFAULT_PREVALENCE:.0%} prevalence (per 1,000)\n")
    L.append("Sensitivity and specificity are model properties. PPV and NPV depend on how rare "
             "the dangerous cases are - at 8% the benign population outnumbers them 11:1.\n")
    L.append("| Model | Effort | Sens % | Spec % | TP | FN | TN | FP | PPV % | NPV % |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for c in cm2:
        L.append(f"| `{c['model']}` | {c['effort']} | {c['sens']:.0f} | {c['spec']:.0f} | "
                 f"{c['tp']:.0f} | {c['fn']:.0f} | {c['tn']:.0f} | {c['fp']:.0f} | "
                 f"{c['ppv']:.0f} | {c['npv']:.1f} |")

    front = pareto_front(rows)
    if front:
        L.append("\n## Cost/score Pareto frontier\n")
        L.append("Nothing else is both cheaper and better:\n")
        for r in front:
            L.append(f"- `{r['model']}` ({r['effort']}): {r['score_mean']:.1f} pts @ "
                     f"${r['cost_mean']:.2f} = {r['score_mean']/r['cost_mean']:.1f} pts/$")

    # Effort deltas: same model, default vs max.
    by_model = {}
    for r in rows:
        by_model.setdefault(r["model"], {})[r["effort"]] = r
    deltas = [(m, e) for m, e in by_model.items() if "default" in e and "max" in e]
    if deltas:
        L.append("\n## What max effort buys\n")
        L.append("Significance is a paired t-test over the shared cases (same model, same "
                 "case, default vs max) - the tightest comparison available here.\n")
        L.append("| Model | Score default -> max | Cost default -> max | $ per extra point | Paired significance |")
        L.append("|---|---|---|---|---|")
        for m, e in sorted(deltas):
            d, x = e["default"], e["max"]
            ds, dc = x["score_mean"] - d["score_mean"], x["cost_mean"] - d["cost_mean"]
            per = f"${dc/ds:.2f}" if ds > 0 else ("no gain" if ds <= 0 else "-")
            tt = paired_test(x, d)
            sig = sig_label(tt[3]) if tt else "-"
            L.append(f"| `{m}` | {d['score_mean']:.1f} -> {x['score_mean']:.1f} ({ds:+.1f}) | "
                     f"${d['cost_mean']:.2f} -> ${x['cost_mean']:.2f} ({dc:+.2f}) | {per} | {sig} |")

    # Every arm against the leader, paired on case.
    if len(rows) > 1:
        best = max(rows, key=lambda r: r["score_mean"])
        L.append(f"\n## Is the ranking real? (paired against `{best['model']}` / {best['effort']})\n")
        L.append("Batch-mean differences at n=3 resolve almost nothing; pairing on the case "
                 "controls for case difficulty and is what these verdicts use.\n")
        L.append("| Model | Effort | Score | Paired diff vs leader | Paired significance |")
        L.append("|---|---|---|---|---|")
        for r in sorted(rows, key=lambda x: -x["score_mean"]):
            if r is best:
                L.append(f"| `{r['model']}` | {r['effort']} | {r['score_mean']:.1f} | - | leader |")
                continue
            tt = paired_test(best, r)
            # Report the paired difference itself, not the headline-score gap:
            # the headline weights cases by series, the paired test weights them
            # equally, so quoting one beside the other's p-value would mislead.
            gap = f"-{tt[0]:.1f}" if tt else "-"
            L.append(f"| `{r['model']}` | {r['effort']} | {r['score_mean']:.1f} | "
                     f"{gap} | {sig_label(tt[3]) if tt else '-'} |")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser(description="Aggregate killbench batches across models")
    ap.add_argument("--dir", default="outputs", help="Directory of BATCH_SUMMARY files")
    ap.add_argument("--since", default=None,
                    help="Only include batches with batch_stamp >= this (e.g. 20260902)")
    ap.add_argument("--csv", default=None)
    ap.add_argument("--md", default=None)
    args = ap.parse_args()

    summaries = load_summaries(args.dir, args.since)
    if not summaries:
        print(f"No usable BATCH_SUMMARY files in {args.dir}")
        return
    rows = aggregate(summaries)
    md = to_markdown(rows)
    print(md)
    print(f"({len(summaries)} batches across {len(rows)} model/effort groups)")
    if args.csv:
        write_csv(rows, args.csv)
        print(f"wrote {args.csv}")
    if args.md:
        with open(args.md, "w") as fh:
            fh.write(md)
        print(f"wrote {args.md}")


if __name__ == "__main__":
    main()
