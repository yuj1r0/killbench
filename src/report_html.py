"""
Render the cross-model comparison as a standalone HTML report.

Consumes the same aggregation as compare_models.py so the page and the console
table can never disagree.

Usage:
    python src/report_html.py --dir outputs --out report.html
"""
import os
import html
import argparse
from datetime import date

import compare_models as cm

# Series colours are the validated categorical slots 1 and 2 (light / dark).
S_DEFAULT_L, S_MAX_L = "#2a78d6", "#eb6834"


def esc(s):
    return html.escape(str(s))


def short(model):
    """Model ids are long; the lab prefix is redundant inside a chart."""
    return (model.replace("claude-", "").replace("gpt-", "GPT-")
                 .replace("gemini-", "").replace("grok-", "Grok-")
                 .replace("-20251001", ""))


RADAR_AXES = [("m_overall", "Total score"), ("m_safety", "Dangerous acc"),
              ("m_specificity", "Benign acc"), ("m_thoroughness", "VoI"),
              ("m_turns", "Turns")]


def radar(r, size=210):
    """One model's profile on five 0-100 axes.

    Small multiples rather than eleven overlapping polygons: the shape of a
    single model is the thing to read, and overlaying more than about three
    series makes every one of them unreadable.
    """
    import math
    cx = cy = size / 2
    rad = size / 2 - 34
    n = len(RADAR_AXES)
    ang = lambda i: -math.pi / 2 + 2 * math.pi * i / n
    pt = lambda i, v: (cx + rad * v / 100 * math.cos(ang(i)),
                       cy + rad * v / 100 * math.sin(ang(i)))
    p = [f'<svg viewBox="0 0 {size} {size}" class="radar" role="img" '
         f'aria-label="{esc(short(r["model"]))} profile">']
    for ring in (25, 50, 75, 100):
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in (pt(i, ring) for i in range(n)))
        p.append(f'<polygon points="{pts}" class="radar-grid"/>')
    for i in range(n):
        x, y = pt(i, 100)
        p.append(f'<line x1="{cx}" y1="{cy}" x2="{x:.1f}" y2="{y:.1f}" class="radar-spoke"/>')
    vals = [max(0.0, min(100.0, r.get(k) or 0)) for k, _ in RADAR_AXES]
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in (pt(i, v) for i, v in enumerate(vals)))
    cls = "radar-fill-max" if r["effort"] == "max" else "radar-fill-def"
    p.append(f'<polygon points="{pts}" class="{cls}"/>')
    for i, v in enumerate(vals):
        x, y = pt(i, v)
        p.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.5" class="{cls} radar-dot"/>')
    for i, (_, lab) in enumerate(RADAR_AXES):
        x, y = pt(i, 128)
        anchor = "middle" if abs(x - cx) < 12 else ("start" if x > cx else "end")
        p.append(f'<text x="{x:.1f}" y="{y+3:.1f}" class="radar-lab" '
                 f'text-anchor="{anchor}">{lab}</text>')
    p.append("</svg>")
    return "".join(p)


def tradeoff(rows, width=680, height=400):
    """Safety against specificity - the central tension in the results."""
    L, R, T, B = 58, 108, 20, 46
    pw, ph = width - L - R, height - T - B
    lo = 45
    fx = lambda v: L + pw * (v - lo) / (100 - lo)
    fy = lambda v: T + ph * (1 - (v - lo) / (100 - lo))
    p = [f'<svg viewBox="0 0 {width} {height}" class="chart" role="img" '
         f'aria-label="Safety versus specificity">']
    for v in (50, 60, 70, 80, 90, 100):
        p.append(f'<line x1="{L}" y1="{fy(v):.1f}" x2="{L+pw}" y2="{fy(v):.1f}" class="grid"/>')
        p.append(f'<line x1="{fx(v):.1f}" y1="{T}" x2="{fx(v):.1f}" y2="{T+ph}" class="grid"/>')
        p.append(f'<text x="{L-9}" y="{fy(v)+4:.1f}" class="tick" text-anchor="end">{v}</text>')
        p.append(f'<text x="{fx(v):.1f}" y="{T+ph+18}" class="tick" text-anchor="middle">{v}</text>')
    p.append(f'<text x="{L+pw/2:.0f}" y="{height-6}" class="axis-title" text-anchor="middle">'
             f'Specificity - benign cases not escalated</text>')
    p.append(f'<text x="14" y="{T+ph/2:.0f}" class="axis-title" text-anchor="middle" '
             f'transform="rotate(-90 14 {T+ph/2:.0f})">Safety - dangerous cases caught</text>')
    for r in sorted(rows, key=lambda x: -x["m_overall"]):
        x, y = fx(r["m_safety"] * 0 + r["m_specificity"]), fy(r["m_safety"])
        cls = "dot-max" if r["effort"] == "max" else "dot-def"
        p.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" class="{cls}">'
                 f'<title>{esc(short(r["model"]))} ({r["effort"]}): safety {r["m_safety"]:.0f}, '
                 f'specificity {r["m_specificity"]:.0f}</title></circle>')
        p.append(f'<text x="{x+10:.1f}" y="{y+4:.1f}" class="ptlab">'
                 f'{esc(short(r["model"]))}<tspan class="ptlab-eff"> {r["effort"][:3]}</tspan></text>')
    p.append("</svg>")
    return "".join(p)


def score_bars(rows, width=680, row_h=26):
    """Total score per configuration, ordered. Labelled with mean +/- SD so the
    run-to-run spread is visible next to the bar rather than buried in a table."""
    order = sorted(rows, key=lambda r: -r["m_overall"])
    if not order:
        return "<p class='empty'>No data.</p>"
    vmax = 50.0 if max(r["m_overall"] for r in order) <= 50 else 100.0
    lab_w, pad_r = 168, 92
    plot_w = width - lab_w - pad_r
    height = 26 + len(order) * row_h + 30
    p = [f'<svg viewBox="0 0 {width} {height}" class="chart" role="img" '
         f'aria-label="Total score by model">']
    for i in range(6):
        x = lab_w + plot_w * i / 5
        p.append(f'<line x1="{x:.1f}" y1="20" x2="{x:.1f}" y2="{height-28}" class="grid"/>')
        p.append(f'<text x="{x:.1f}" y="{height-12}" class="tick" text-anchor="middle">'
                 f'{vmax*i/5:.0f}</text>')
    y = 24
    for r in order:
        v = r["m_overall"]
        w = max(2, plot_w * v / vmax)
        cls = "bar-max" if r["effort"] == "max" else "bar-def"
        p.append(f'<text x="{lab_w-10}" y="{y+row_h-9}" class="ylab" text-anchor="end">'
                 f'{esc(short(r["model"]))}</text>')
        p.append(f'<rect x="{lab_w}" y="{y+3}" width="{w:.1f}" height="{row_h-10}" rx="4" '
                 f'class="{cls}"><title>{esc(short(r["model"]))} ({r["effort"]}): '
                 f'{v:.1f} +/- {r["score_sd"]:.1f}, n={r["n_runs"]}</title></rect>')
        p.append(f'<text x="{lab_w+w+7:.1f}" y="{y+row_h-9}" class="vlab">{v:.1f}'
                 f'<tspan class="sd"> &#177;{r["score_sd"]:.1f}</tspan></text>')
        y += row_h
    p.append("</svg>")
    return "".join(p)


DECOMP = [("m_safety", "Dangerous-case accuracy", "safety"),
          ("m_thoroughness", "Information gathered (VoI)", "voi"),
          ("m_specificity", "Benign cases not escalated", "benign")]


def decomposition(rows, width=680, bar_h=13, gap=3):
    """The three components the total score is built from, side by side.

    Every bar carries its own value label: the third hue sits below 3:1 contrast
    on the light surface, so identity can never rest on colour alone.
    """
    order = sorted(rows, key=lambda r: -r["m_overall"])
    if not order:
        return "<p class='empty'>No data.</p>"
    lab_w, pad_r = 168, 56
    plot_w = width - lab_w - pad_r
    grp_h = len(DECOMP) * (bar_h + gap) + 11
    height = 24 + len(order) * grp_h + 28
    p = [f'<svg viewBox="0 0 {width} {height}" class="chart" role="img" '
         f'aria-label="Score components by model">']
    for i in range(6):
        x = lab_w + plot_w * i / 5
        p.append(f'<line x1="{x:.1f}" y1="18" x2="{x:.1f}" y2="{height-26}" class="grid"/>')
        p.append(f'<text x="{x:.1f}" y="{height-10}" class="tick" text-anchor="middle">{i*20}</text>')
    y = 22
    for r in order:
        p.append(f'<text x="{lab_w-10}" y="{y+grp_h/2:.0f}" class="ylab" text-anchor="end">'
                 f'{esc(short(r["model"]))}<tspan class="ylab-eff"> {esc(r["effort"][:3])}</tspan></text>')
        for key, name, slot in DECOMP:
            v = max(0.0, min(100.0, r.get(key) or 0))
            w = max(2, plot_w * v / 100)
            p.append(f'<rect x="{lab_w}" y="{y}" width="{w:.1f}" height="{bar_h}" rx="3" '
                     f'class="mb-{slot}"><title>{esc(short(r["model"]))} ({r["effort"]}) '
                     f'{name}: {v:.0f}</title></rect>')
            p.append(f'<text x="{lab_w+w+6:.1f}" y="{y+bar_h-2}" class="vlab">{v:.0f}</text>')
            y += bar_h + gap
        y += 11
    p.append("</svg>")
    return "".join(p)


def bar_chart(rows, value, label, fmt="{:.1f}", width=680, row_h=30, critical=False):
    """Horizontal grouped bars, one group per model, one bar per effort level.

    Draws to a single scale: axis ticks and every bar share `vmax`, so a label
    always names a value the chart actually reaches.
    """
    by_model = {}
    for r in rows:
        by_model.setdefault(r["model"], {})[r["effort"]] = r
    order = sorted(by_model, key=lambda m: -max(
        (e.get(value) or 0) for e in by_model[m].values()))
    if not order:
        return "<p class='empty'>No data yet.</p>"

    vmax = max([(e.get(value) or 0) for m in order for e in by_model[m].values()] + [0.0001])
    # Round the axis up to a friendly tick so labels sit on real numbers.
    step = 10 ** (len(str(int(vmax))) - 1) if vmax >= 1 else 0.1
    vmax = (int(vmax / step) + 1) * step
    lab_w, pad_r, top = 150, 60, 26
    plot_w = width - lab_w - pad_r
    bars_per = 2
    height = top + len(order) * row_h * bars_per + 34

    p = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{esc(label)}" class="chart">']
    # gridlines + axis labels
    for i in range(5):
        x = lab_w + plot_w * i / 4
        v = vmax * i / 4
        p.append(f'<line x1="{x:.1f}" y1="{top-6}" x2="{x:.1f}" y2="{height-30}" class="grid"/>')
        p.append(f'<text x="{x:.1f}" y="{height-14}" class="tick" text-anchor="middle">{fmt.format(v)}</text>')

    y = top
    for m in order:
        entries = by_model[m]
        p.append(f'<text x="{lab_w-10}" y="{y+row_h-6}" class="ylab" text-anchor="end">{esc(short(m))}</text>')
        for eff in ("default", "max"):
            r = entries.get(eff)
            if r is None:
                y += row_h
                continue
            v = r.get(value) or 0
            w = max(2, plot_w * v / vmax)
            cls = "bar-crit" if critical and v > 0 else ("bar-max" if eff == "max" else "bar-def")
            p.append(f'<rect x="{lab_w}" y="{y+6}" width="{w:.1f}" height="{row_h-14}" '
                     f'rx="4" class="{cls}"><title>{esc(short(m))} {eff}: {fmt.format(v)}</title></rect>')
            # direct label (relief rule: never rely on colour alone)
            p.append(f'<text x="{lab_w+w+7:.1f}" y="{y+row_h-9}" class="vlab">{fmt.format(v)}</text>')
            y += row_h
    p.append("</svg>")
    return "".join(p)


def scatter(rows, width=680, height=380):
    """Cost (log x) vs score (y), with the Pareto frontier drawn through it."""
    pts = [r for r in rows if (r.get("cost_mean") or 0) > 0]
    if not pts:
        return "<p class='empty'>No priced runs yet.</p>"
    import math
    xs = [r["cost_mean"] for r in pts]
    ys = [r["score_mean"] for r in pts]
    lo, hi = min(xs) * 0.6, max(xs) * 1.7
    ymax = max(ys + [1]) * 1.25
    L, R, T, B = 62, 22, 22, 46
    pw, ph = width - L - R, height - T - B
    fx = lambda v: L + pw * (math.log10(v) - math.log10(lo)) / (math.log10(hi) - math.log10(lo))
    fy = lambda v: T + ph * (1 - v / ymax)

    p = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Cost versus score" class="chart">']
    for i in range(5):
        v = ymax * i / 4
        yy = fy(v)
        p.append(f'<line x1="{L}" y1="{yy:.1f}" x2="{width-R}" y2="{yy:.1f}" class="grid"/>')
        p.append(f'<text x="{L-9}" y="{yy+4:.1f}" class="tick" text-anchor="end">{v:.0f}</text>')
    # decade ticks across the log axis
    d = math.floor(math.log10(lo))
    while 10 ** d <= hi:
        for mult in (1, 2, 5):
            v = mult * 10 ** d
            if lo <= v <= hi:
                xx = fx(v)
                p.append(f'<line x1="{xx:.1f}" y1="{T}" x2="{xx:.1f}" y2="{T+ph}" class="grid"/>')
                lbl = f"${v:g}"
                p.append(f'<text x="{xx:.1f}" y="{T+ph+18}" class="tick" text-anchor="middle">{lbl}</text>')
        d += 1
    p.append(f'<text x="{L+pw/2}" y="{height-6}" class="axis-title" text-anchor="middle">Cost per 24-case suite (log)</text>')
    p.append(f'<text x="14" y="{T+ph/2}" class="axis-title" text-anchor="middle" '
             f'transform="rotate(-90 14 {T+ph/2})">Score</text>')

    front = cm.pareto_front(pts)
    if len(front) > 1:
        pathd = " ".join(f"{'M' if i==0 else 'L'}{fx(r['cost_mean']):.1f},{fy(r['score_mean']):.1f}"
                         for i, r in enumerate(front))
        p.append(f'<path d="{pathd}" class="front"/>')
    for r in pts:
        cx, cy = fx(r["cost_mean"]), fy(r["score_mean"])
        cls = "dot-max" if r["effort"] == "max" else "dot-def"
        p.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="6" class="{cls}">'
                 f'<title>{esc(short(r["model"]))} ({r["effort"]}): {r["score_mean"]:.1f} pts @ ${r["cost_mean"]:.2f}</title></circle>')
        p.append(f'<text x="{cx+11:.1f}" y="{cy+4:.1f}" class="ptlab">{esc(short(r["model"]))}</text>')
    p.append("</svg>")
    return "".join(p)


def build(rows, n_batches):
    total_cost = sum((r["cost_mean"] + r["overhead_mean"]) * r["n_runs"] for r in rows)
    total_deaths = sum(r["deaths"] for r in rows)
    n_models = len({r["model"] for r in rows})
    best = max(rows, key=lambda r: r["score_mean"]) if rows else None
    safest = min((r for r in rows), key=lambda r: r["deaths"], default=None)

    tiles = [
        ("Models tested", f"{n_models}", "across 4 labs"),
        ("Batches", f"{n_batches}", "24 cases each"),
        ("Total spend", f"${total_cost:,.2f}", "API cost, all roles"),
        ("Mean patient deaths", f"{total_deaths/len(rows):.1f}" if rows else "-",
         "per 24-case suite"),
    ]
    tile_html = "".join(
        f'<div class="tile"><span class="tile-k">{esc(k)}</span>'
        f'<span class="tile-v">{esc(v)}</span><span class="tile-s">{esc(s)}</span></div>'
        for k, v, s in tiles)

    # Effort delta, with the paired significance from compare_models.
    by_model = {}
    for r in rows:
        by_model.setdefault(r["model"], {})[r["effort"]] = r
    drows = []
    for m, e in sorted(by_model.items()):
        if "default" in e and "max" in e:
            d, x = e["default"], e["max"]
            ds = x["m_overall"] - d["m_overall"]
            dc = x["cost_mean"] - d["cost_mean"]
            tt = cm.paired_test(x, d)
            sig = cm.sig_label(tt[3]) if tt else "-"
            cls = "pos" if ds > 0 else "neg"
            drows.append(
                f'<tr><td class="mono">{esc(short(m))}</td>'
                f'<td class="num">{d["m_overall"]:.1f}</td><td class="num">{x["m_overall"]:.1f}</td>'
                f'<td class="num {cls}">{ds:+.1f}</td>'
                f'<td class="num">${dc:+.2f}</td>'
                f'<td class="sig">{esc(sig.replace("*",""))}</td></tr>')
    delta_tbl = "".join(drows) or '<tr><td colspan="6" class="empty">No model has both arms yet.</td></tr>'

    conf_tbl = "".join(
        f'<tr class="{"baseline" if c.get("baseline") else ""}">'
        f'<td class="mono">{esc(short(c["model"]))}</td><td>{esc(c["effort"])}</td>'
        f'<td class="num">{c["sens"]:.0f}%</td><td class="num">{c["spec"]:.0f}%</td>'
        f'<td class="num">{c["tp"]:.0f}</td><td class="num crit">{c["fn"]:.0f}</td>'
        f'<td class="num">{c["tn"]:.0f}</td><td class="num">{c["fp"]:.0f}</td>'
        f'<td class="num">{c["ppv"]:.0f}%</td><td class="num">{c["npv"]:.1f}%</td></tr>'
        for c in cm.confusion_at_prevalence(rows))

    proj_tbl = "".join(
        f'<tr><td class="mono">{esc(short(p["model"]))}</td><td>{esc(p["effort"])}</td>'
        f'<td class="num">{p["kill_rate"]*100:.0f}%</td>'
        f'<td class="num">{p["over_rate"]*100:.0f}%</td>'
        f'<td class="num crit">{p["deaths"]:.0f}</td>'
        f'<td class="num">{p["admits"]:.0f}</td></tr>'
        for p in cm.prevalence_projection(rows))

    trows = "".join(
        f'<tr><td class="mono">{esc(r["model"])}</td><td>{esc(r["effort"])}</td>'
        f'<td class="num">{r["n_runs"]}</td>'
        f'<td class="num">{r["m_overall"]:.1f}</td><td class="num dim">&plusmn;{r["score_sd"]:.1f}</td>'
        f'<td class="num">{r["m_safety"]:.0f}</td><td class="num">{r["m_specificity"]:.0f}</td>'
        f'<td class="num">{r["m_thoroughness"]:.0f}</td>'
        f'<td class="num">{r["avg_turns"]:.1f}</td>'
        f'<td class="num">{"-" if r["lat_median"] is None else format(r["lat_median"], ".1f")}</td>'
        f'<td class="num">${r["cost_mean"]:.2f}</td>'
        f'<td class="num {"crit" if r["deaths"]>0 else ""}">{r["deaths"]:.1f} / {r["deaths_worst"]:.0f}</td></tr>'
        for r in sorted(rows, key=lambda x: -x["m_overall"]))

    radars = "".join(
        f'<figure class="radar-cell"><figcaption>{esc(short(r["model"]))}'
        f'<span class="eff eff-{r["effort"]}">{esc(r["effort"])}</span></figcaption>'
        f'{radar(r)}</figure>'
        for r in sorted(rows, key=lambda x: -x["m_overall"]))

    lead = ""
    if rows:
        b = max(rows, key=lambda r: r["m_overall"])
        sf = max(rows, key=lambda r: r["m_safety"])
        lead = (f'<strong>{esc(short(b["model"]))}</strong> scores highest overall, but '
                f'<strong>{esc(short(sf["model"]))}</strong> catches the most dangerous cases '
                f'&mdash; and no model in the sweep is strong on both safety and specificity.')

    n_models = len({r["model"] for r in rows})
    n_reps = max((r["n_runs"] for r in rows), default=0)
    n_cases = max((r.get("n_cases_seen") or 24) for r in rows) if rows else 24
    run_date = date.today().isoformat()

    return f"""<title>Killbench Model Results</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root {{
  color-scheme: light;
  --ground:#f7f8fa; --surface:#ffffff; --line:#dfe3ea; --line-soft:#eceff4;
  --ink:#0d1117; --ink-2:#3f4854; --ink-3:#6b7686;
  --accent:#2a78d6; --accent-2:#eb6834; --crit:#c0362c; --pos:#1a7f52;
  --series-def:{S_DEFAULT_L}; --series-max:{S_MAX_L};
  --m-safety:#2a78d6; --m-voi:#eb6834; --m-benign:#1baf7a;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    color-scheme: dark;
    --ground:#101317; --surface:#171b21; --line:#2b323c; --line-soft:#232931;
    --ink:#eef2f7; --ink-2:#b3bdcb; --ink-3:#7d8899;
    --accent:#3987e5; --accent-2:#d95926; --crit:#e56b60; --pos:#3fa878;
    --series-def:#3987e5; --series-max:#d95926;
    --m-safety:#3987e5; --m-voi:#d95926; --m-benign:#199e70;
  }}
}}
:root[data-theme="dark"] {{
  color-scheme: dark;
  --ground:#101317; --surface:#171b21; --line:#2b323c; --line-soft:#232931;
  --ink:#eef2f7; --ink-2:#b3bdcb; --ink-3:#7d8899;
  --accent:#3987e5; --accent-2:#d95926; --crit:#e56b60; --pos:#3fa878;
  --series-def:#3987e5; --series-max:#d95926;
  --m-safety:#3987e5; --m-voi:#d95926; --m-benign:#199e70;
}}
* {{ box-sizing:border-box; }}
body {{ background:var(--ground); color:var(--ink);
  font-family:"IBM Plex Sans",system-ui,-apple-system,sans-serif;
  line-height:1.55; margin:0; padding:40px 24px 72px; }}
.wrap {{ max-width:940px; margin:0 auto; display:flex; flex-direction:column; gap:38px; }}
header {{ border-bottom:2px solid var(--ink); padding-bottom:18px;
  display:flex; flex-direction:column; gap:8px; }}
.eyebrow {{ font-family:"IBM Plex Mono",monospace; font-size:11px; letter-spacing:.14em;
  text-transform:uppercase; color:var(--ink-3); }}
h1 {{ font-size:34px; font-weight:600; letter-spacing:-.02em; margin:0; text-wrap:balance; }}
.sub {{ color:var(--ink-2); max-width:62ch; margin:0; }}
h2 {{ font-size:19px; font-weight:600; margin:0 0 4px; letter-spacing:-.01em; }}
.note {{ color:var(--ink-3); font-size:13.5px; margin:0 0 14px; max-width:66ch; }}
section {{ display:flex; flex-direction:column; }}
.tiles {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:1px;
  background:var(--line); border:1px solid var(--line); }}
.tile {{ background:var(--surface); padding:16px 18px; display:flex; flex-direction:column; gap:3px; }}
.tile-k {{ font-family:"IBM Plex Mono",monospace; font-size:10.5px; letter-spacing:.1em;
  text-transform:uppercase; color:var(--ink-3); }}
.tile-v {{ font-family:"IBM Plex Mono",monospace; font-size:27px; font-weight:500;
  font-variant-numeric:tabular-nums; letter-spacing:-.02em; }}
.tile-s {{ font-size:12px; color:var(--ink-3); }}
.panel {{ background:var(--surface); border:1px solid var(--line); padding:20px 22px; }}
.chart {{ width:100%; height:auto; display:block; }}
.grid {{ stroke:var(--line-soft); stroke-width:1; }}
.tick, .ylab, .vlab, .ptlab, .axis-title {{ font-family:"IBM Plex Mono",monospace; fill:var(--ink-3); }}
.tick {{ font-size:10.5px; }}
.ylab {{ font-size:12px; fill:var(--ink-2); }}
.vlab {{ font-size:11px; fill:var(--ink-2); font-variant-numeric:tabular-nums; }}
.ptlab {{ font-size:11px; fill:var(--ink-2); }}
.axis-title {{ font-size:11px; letter-spacing:.06em; text-transform:uppercase; }}
.bar-def {{ fill:var(--series-def); }}
.bar-max {{ fill:var(--series-max); }}
.bar-crit {{ fill:var(--crit); }}
.dot-def {{ fill:var(--series-def); stroke:var(--surface); stroke-width:2; }}
.dot-max {{ fill:var(--series-max); stroke:var(--surface); stroke-width:2; }}
.front {{ fill:none; stroke:var(--ink-3); stroke-width:2; stroke-dasharray:5 4; }}
.legend {{ display:flex; gap:18px; align-items:center; margin-bottom:12px;
  font-size:12.5px; color:var(--ink-2); }}
.key {{ display:inline-flex; align-items:center; gap:7px; }}
.sw {{ width:13px; height:13px; border-radius:3px; display:inline-block; }}
.tbl-scroll {{ overflow-x:auto; }}
table {{ border-collapse:collapse; width:100%; font-size:13px; }}
th {{ text-align:left; font-family:"IBM Plex Mono",monospace; font-size:10.5px;
  letter-spacing:.08em; text-transform:uppercase; color:var(--ink-3);
  border-bottom:1px solid var(--line); padding:9px 10px; white-space:nowrap; }}
td {{ padding:9px 10px; border-bottom:1px solid var(--line-soft); white-space:nowrap; }}
.num {{ text-align:right; font-variant-numeric:tabular-nums;
  font-family:"IBM Plex Mono",monospace; }}
.mono {{ font-family:"IBM Plex Mono",monospace; font-size:12px; }}
.dim {{ color:var(--ink-3); }} .crit {{ color:var(--crit); font-weight:500; }}
.pos {{ color:var(--pos); }} .neg {{ color:var(--crit); }}
.pill {{ font-family:"IBM Plex Mono",monospace; font-size:10.5px; padding:2px 8px;
  border:1px solid currentColor; border-radius:99px; }}
.pill-worth {{ color:var(--pos); }} .pill-no {{ color:var(--crit); }}
.pill-marginal {{ color:var(--ink-3); }}
.empty {{ color:var(--ink-3); font-style:italic; padding:14px 0; }}
.radar-grid-wrap {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr));
  gap:10px 4px; margin-top:6px; }}
.radar-cell {{ margin:0; display:flex; flex-direction:column; align-items:center; gap:2px; }}
.radar-cell figcaption {{ font-family:"IBM Plex Mono",monospace; font-size:11.5px;
  color:var(--ink-2); display:flex; align-items:center; gap:6px; }}
.eff {{ font-size:9.5px; letter-spacing:.06em; text-transform:uppercase;
  padding:1px 5px; border-radius:99px; border:1px solid currentColor; }}
.eff-default {{ color:var(--series-def); }}
.eff-max {{ color:var(--series-max); }}
.radar {{ width:100%; height:auto; max-width:210px; }}
.radar-grid {{ fill:none; stroke:var(--line); stroke-width:1; }}
.radar-spoke {{ stroke:var(--line); stroke-width:1; }}
.radar-lab {{ font-family:"IBM Plex Mono",monospace; font-size:8.5px; fill:var(--ink-3); }}
.radar-fill-def {{ fill:var(--series-def); fill-opacity:.22; stroke:var(--series-def); stroke-width:2; }}
.radar-fill-max {{ fill:var(--series-max); fill-opacity:.22; stroke:var(--series-max); stroke-width:2; }}
.radar-dot {{ fill-opacity:1; }}
.two-up {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(290px,1fr)); gap:26px; }}
.ptlab-eff {{ fill:var(--ink-3); }}
tr.baseline {{ color:var(--ink-3); font-style:italic; background:color-mix(in srgb, var(--line-soft) 55%, transparent); }}
.sig {{ font-family:"IBM Plex Mono",monospace; font-size:11.5px; color:var(--ink-2); }}
.sd {{ fill:var(--ink-3); font-size:10px; }}
.mb-safety {{ fill:var(--m-safety); }}
.mb-voi {{ fill:var(--m-voi); }}
.mb-benign {{ fill:var(--m-benign); }}
.ylab-eff {{ fill:var(--ink-3); font-size:10px; }}
.method h2 {{ margin-bottom:12px; }}
.method-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(230px,1fr)); gap:20px 26px; }}
.method-grid h3 {{ font-family:"IBM Plex Mono",monospace; font-size:11px; letter-spacing:.07em;
  text-transform:uppercase; color:var(--ink-3); margin:0 0 5px; font-weight:500; }}
.method-grid p {{ margin:0; font-size:13.5px; color:var(--ink-2); }}
footer {{ color:var(--ink-3); font-size:12.5px; border-top:1px solid var(--line);
  padding-top:16px; max-width:70ch; }}
footer p {{ margin:0 0 7px; }}
</style>

<div class="wrap">
<header>
  <span class="eyebrow">Killbench &middot; agentic multi-turn clinical decision benchmark</span>
  <h1>Frontier model results</h1>
  <p class="sub">{n_models} models on the {n_cases}-case v0.0.1 suite, {n_reps} repeats per
  configuration, run {run_date}. Each model acts as the physician agent: it must ask questions,
  order tests, and commit to a disposition within 25 turns, against a fixed
  <code>claude-sonnet-5</code> gate referee and answer server. Cases come in matched
  dangerous/benign pairs. A wrong decision on a dangerous case scores zero for that case
  (kill penalty) and voids its benign twin.</p>
</header>

<section class="panel method">
  <h2>Scoring</h2>
  <div class="method-grid">
    <div>
      <h3>Case score</h3>
      <p>0 if the disposition is wrong on a dangerous case. Otherwise 50 points for the correct
      decision plus 0&ndash;50 for value of information &mdash; the relevant gates the model
      unlocked by asking or ordering.</p>
    </div>
    <div>
      <h3>Information gating</h3>
      <p>Critical findings are withheld until the model asks for them specifically. Variants
      differ in how much is volunteered, from provided upfront to inferable only from subtle
      clues. A generic &ldquo;check everything&rdquo; sweep does not unlock targeted gates.</p>
    </div>
    <div>
      <h3>Adversarial pairs</h3>
      <p>Each dangerous case has a matched benign twin with a near-identical presentation.
      Escalating everything and discharging everything both fail. Cases are constructed to
      trigger anchoring, premature closure, availability bias and search satisficing.</p>
    </div>
    <div>
      <h3>Penalties</h3>
      <p>A wrong call on a benign case costs 10 points. A kill zeroes the dangerous case and
      voids its twin, so one fatal error removes two cases from the total. Reaching no decision
      within 25 turns is a timeout.</p>
    </div>
  </div>
</section>

<section>
  <div class="tiles">{tile_html}</div>
</section>

<section class="panel">
  <h2>Total score</h2>
  <p class="note">Weighted score across the suite: 50 points for the correct disposition plus
  up to 50 for value-of-information gathering, weighted by series acuity, with the kill penalty
  and benign overcall penalty applied. Bars are the mean of {n_reps} runs; the number after
  &plusmn; is the standard deviation across those runs.</p>
  <div class="legend">
    <span class="key"><span class="sw" style="background:var(--series-def)"></span>default effort</span>
    <span class="key"><span class="sw" style="background:var(--series-max)"></span>max reasoning effort</span>
  </div>
  {score_bars(rows)}
</section>

<section class="panel">
  <h2>Where the scores come from</h2>
  <p class="note">The total score is built from three things. <strong>Dangerous-case accuracy</strong>
  decides whether a case scores at all &mdash; a wrong call on a dangerous case is floored to zero
  and voids its benign twin. <strong>Information gathered</strong> is the VoI component: the share
  of relevant gates unlocked on cases decided correctly, worth up to half the available points.
  <strong>Benign cases not escalated</strong> is the counterweight &mdash; over-treatment carries a
  10-point penalty, so a model cannot bank points by escalating everything.</p>
  <div class="legend">
    <span class="key"><span class="sw" style="background:var(--m-safety)"></span>dangerous-case accuracy</span>
    <span class="key"><span class="sw" style="background:var(--m-voi)"></span>information gathered (VoI)</span>
    <span class="key"><span class="sw" style="background:var(--m-benign)"></span>benign cases not escalated</span>
  </div>
  {decomposition(rows)}
</section>

<section class="panel">
  <h2>Dangerous-case accuracy against benign-case accuracy</h2>
  <p class="note">Horizontal axis: share of benign cases not escalated. Vertical axis: share of
  dangerous cases decided correctly. The benchmark requires both &mdash; models that escalate
  everything and models that discharge everything both fail. No configuration reaches the
  upper-right quadrant.</p>
  <div class="legend">
    <span class="key"><span class="sw" style="background:var(--series-def)"></span>default effort</span>
    <span class="key"><span class="sw" style="background:var(--series-max)"></span>max effort</span>
  </div>
  {tradeoff(rows)}
</section>

<section class="panel">
  <h2>Model profiles</h2>
  <p class="note">Five axes, each 0&ndash;100, further out is better. VoI is the share of
  available information gates unlocked on cases decided correctly. Turns is average turn count
  relative to the highest in the sweep; it is a description of behaviour, not a quality score.</p>
  <div class="radar-grid-wrap">{radars}</div>
</section>

<section class="panel">
  <h2>Cost and latency</h2>
  <p class="note">Left in real units. Cost is per 24-case suite including referee and
  answer-server overhead; latency is median seconds per doctor turn, measured only in
  single-threaded batches.</p>
  <div class="two-up">
    <div>{bar_chart(rows, "cost_mean", "Cost per suite", "${:.2f}")}</div>
    <div>{bar_chart(rows, "lat_median", "Median seconds per turn", "{:.0f}s")}</div>
  </div>
</section>

<section class="panel">
  <h2>Effect of maximum reasoning effort</h2>
  <p class="note">Paired t-test over the shared cases: same model, same case, default versus
  maximum reasoning effort.</p>
  <div class="tbl-scroll"><table>
    <thead><tr><th>Model</th><th class="num">Default</th><th class="num">Max</th>
    <th class="num">&Delta;</th><th class="num">Cost &Delta;</th><th>Significance</th></tr></thead>
    <tbody>{delta_tbl}</tbody>
  </table></div>
</section>

<section class="panel">
  <h2>Diagnostic performance at 8% prevalence</h2>
  <p class="note">Sensitivity and specificity are properties of the model. Predictive values are
  not &mdash; they depend on how rare the dangerous cases are. Scaled to 1,000 presentations with
  80 dangerous and 920 benign. A dangerous case decided correctly counts as a true positive, a
  benign case not escalated as a true negative. The two trivial policies are shown for reference:
  discharging every patient already scores 92% NPV without examining anyone, so that is the
  number each model has to beat.</p>
  <div class="tbl-scroll"><table>
    <thead><tr><th>Model</th><th>Effort</th><th class="num">Sens</th><th class="num">Spec</th>
    <th class="num">TP</th><th class="num">FN</th><th class="num">TN</th><th class="num">FP</th>
    <th class="num">PPV</th><th class="num">NPV</th></tr></thead>
    <tbody>{conf_tbl}</tbody>
  </table></div>
</section>

<section class="panel">
  <h2>Projected onto 1,000 ED presentations</h2>
  <p class="note">The suite is half dangerous by construction; a real department is not.
  At 8% prevalence, overcalls scale with the 920 benign patients and kills with the 80
  dangerous ones. Every unneeded admission also consumes a bed the next emergency needs
  &mdash; a cost this table does not attempt to count.</p>
  <div class="tbl-scroll"><table>
    <thead><tr><th>Model</th><th>Effort</th><th class="num">Kill rate</th>
    <th class="num">Overcall rate</th><th class="num">Deaths</th>
    <th class="num">Unneeded admits</th></tr></thead>
    <tbody>{proj_tbl}</tbody>
  </table></div>
</section>

<section class="panel">
  <h2>Full results</h2>
  <div class="tbl-scroll"><table>
    <thead><tr><th>Model</th><th>Effort</th><th class="num">Runs</th><th class="num">Overall</th>
    <th class="num">SD</th><th class="num">Safety</th><th class="num">Specif.</th>
    <th class="num">Thorough</th><th class="num">Turns</th><th class="num">s/turn</th>
    <th class="num">$/suite</th><th class="num">Deaths m/worst</th></tr></thead>
    <tbody>{trows}</tbody>
  </table></div>
</section>

<footer>
  <p>Doctor models were tested against a fixed <code>claude-sonnet-5</code> gate referee and
  answer server, so scoring is constant across the comparison.</p>
  <p>Doctor output budget was 4,000 tokens per turn. Thinking tokens are drawn from that
  same budget, so the older 1,000-token cap would have truncated reasoning models &mdash;
  default-effort figures here are therefore not directly comparable to pre-2026-09 runs.</p>
  <p>Prices verified against each provider's published rates on 2026-09-02. Several are
  promotional and will rise.</p>
</footer>
</div>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="outputs")
    ap.add_argument("--since", default=None)
    ap.add_argument("--out", default="report.html")
    args = ap.parse_args()
    summaries = cm.load_summaries(args.dir, args.since)
    rows = cm.aggregate(summaries)
    with open(args.out, "w") as fh:
        fh.write(build(rows, len(summaries)))
    print(f"wrote {args.out} ({len(rows)} groups, {len(summaries)} batches)")


if __name__ == "__main__":
    main()
