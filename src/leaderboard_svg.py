"""
Render the leaderboard as a static SVG for the README.

Two files are written, light and dark, because GitHub strips <style> blocks and
ignores prefers-color-scheme inside an <img>: the README picks between them with
a <picture> element instead. Every attribute is therefore a literal colour.

Usage:
    python src/leaderboard_svg.py --dir outputs --since 20260902_17 --out-dir docs
"""
import os
import html
import argparse

import compare_models as cm

THEMES = {
    "light": dict(ink="#0d1117", ink2="#3f4854", ink3="#6b7686", grid="#e3e7ee",
                  axis="#c3cad6", bg="none", defc="#2a78d6", maxc="#eb6834"),
    "dark":  dict(ink="#eef2f7", ink2="#b3bdcb", ink3="#7d8899", grid="#2b323c",
                  axis="#3a434f", bg="none", defc="#3987e5", maxc="#d95926"),
}

FONT = "ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"


def short(m):
    return (m.replace("claude-", "").replace("gpt-", "GPT-")
             .replace("gemini-", "").replace("grok-", "Grok-")
             .replace("-20251001", ""))


def render(rows, theme, width=860, row_h=30):
    t = THEMES[theme]
    order = sorted(rows, key=lambda r: -r["m_overall"])
    lab_w, pad_r, top = 210, 112, 34
    plot_w = width - lab_w - pad_r
    height = top + len(order) * row_h + 34
    vmax = 50.0
    e = html.escape
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
         f'viewBox="0 0 {width} {height}" font-family="{FONT}" role="img" '
         f'aria-label="Killbench leaderboard">']
    o.append(f'<text x="0" y="14" font-size="12" font-weight="600" fill="{t["ink"]}">'
             f'Killbench v0.0.1 &#183; total score (24 cases, mean of 3 runs)</text>')
    # legend
    o.append(f'<rect x="{lab_w}" y="21" width="9" height="9" rx="2" fill="{t["defc"]}"/>'
             f'<text x="{lab_w+14}" y="29" font-size="10.5" fill="{t["ink3"]}">default effort</text>')
    o.append(f'<rect x="{lab_w+108}" y="21" width="9" height="9" rx="2" fill="{t["maxc"]}"/>'
             f'<text x="{lab_w+122}" y="29" font-size="10.5" fill="{t["ink3"]}">max reasoning effort</text>')
    for i in range(6):
        x = lab_w + plot_w * i / 5
        o.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{height-30}" '
                 f'stroke="{t["grid"]}" stroke-width="1"/>')
        o.append(f'<text x="{x:.1f}" y="{height-14}" font-size="10" fill="{t["ink3"]}" '
                 f'text-anchor="middle">{vmax*i/5:.0f}</text>')
    y = top + 2
    for r in order:
        v = r["m_overall"]
        w = max(2, plot_w * v / vmax)
        col = t["maxc"] if r["effort"] == "max" else t["defc"]
        o.append(f'<text x="{lab_w-10}" y="{y+row_h-11}" font-size="11.5" fill="{t["ink2"]}" '
                 f'text-anchor="end">{e(short(r["model"]))}'
                 f'<tspan fill="{t["ink3"]}" font-size="10" dx="4">{e(r["effort"][:3])}</tspan></text>')
        o.append(f'<rect x="{lab_w}" y="{y}" width="{w:.1f}" height="{row_h-14}" rx="3" fill="{col}"/>')
        o.append(f'<text x="{lab_w+w+7:.1f}" y="{y+row_h-13}" font-size="11" fill="{t["ink2"]}">'
                 f'{v:.1f}<tspan fill="{t["ink3"]}" font-size="9.5" dx="3">&#177;{r["score_sd"]:.1f}</tspan></text>')
        y += row_h
    o.append(f'<line x1="{lab_w}" y1="{top}" x2="{lab_w}" y2="{height-30}" '
             f'stroke="{t["axis"]}" stroke-width="1"/>')
    o.append("</svg>")
    return "".join(o)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="outputs")
    ap.add_argument("--since", default=None)
    ap.add_argument("--out-dir", default="docs")
    args = ap.parse_args()
    rows = cm.aggregate(cm.load_summaries(args.dir, args.since))
    os.makedirs(args.out_dir, exist_ok=True)
    for theme in THEMES:
        path = os.path.join(args.out_dir, f"leaderboard-{theme}.svg")
        with open(path, "w") as fh:
            fh.write(render(rows, theme))
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
