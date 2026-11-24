#!/usr/bin/env python3
"""Render eval/real-runs/{findings,runs}.jsonl as one offline HTML page (no CDN: the data is private).
usage: eval/report.py [data-dir]   -> <data-dir>/report.html"""
import json, sys, datetime
from collections import Counter, defaultdict
from html import escape as e
from pathlib import Path

d = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent / "real-runs")
load = lambda n: [json.loads(l) for l in (d / n).read_text().splitlines() if l.strip()] if (d / n).exists() else []
F, R = load("findings.jsonl"), load("runs.jsonl")
OUT = ["accepted", "partial", "declined", "pending"]  # status colors, always shown with their label

def bars(key):
    """One stacked bar per value of `key`, segments by outcome, widths relative to the largest group."""
    g = defaultdict(Counter)
    for f in F: g[f.get(key) or "-"][f["outcome"]] += 1
    top = max((sum(c.values()) for c in g.values()), default=1)
    rows = []
    for k, c in sorted(g.items(), key=lambda kv: -sum(kv[1].values())):
        n = sum(c.values())
        segs = "".join(f'<i class="s-{o}" style="flex:{c[o]}" title="{e(k)}: {c[o]} {o}"></i>' for o in OUT if c[o])
        rows.append(f'<div class="row"><span>{e(k)}</span><div class="bar" style="width:{n / top * 100:.1f}%">{segs}</div>'
                    f'<b>{c["accepted"]}/{n}</b></div>')
    return "".join(rows)

def tile(label, value, sub=""):
    return f'<div class="tile"><span>{label}</span><strong>{value}</strong><small>{sub}</small></div>'

def link(u, t): return f'<a href="{e(u)}">{t}</a>' if u else ""

n = len(F); acc = sum(f["outcome"] == "accepted" for f in F)
nosub = sum(r["no_subagents"] for r in R)
by_v = defaultdict(list)
for r in R: by_v[r.get("skill_version", "?")].append(r)

vrows = "".join(
    f'<tr><td><code>{e(v)}</code></td><td>{len(rs)}</td><td>{sum(r["no_subagents"] for r in rs)}</td>'
    f'<td>{sum(r["denied"] for r in rs)}</td><td>${sum(r["cost"] for r in rs) / len(rs):.2f}</td></tr>'
    for v, rs in by_v.items())
frows = "".join(
    f'<tr><td>{e(f["date"])}</td><td>{e(f["repo"])}#{f["pr"]}</td><td class="path">{e(f["path"] or "(body)")}{":" + str(f["line"]) if f["line"] else ""}</td>'
    f'<td>{e(f["bucket"])}</td><td>{e(f["severity"])}</td><td>{e(f["kind"])}</td>'
    f'<td><span class="pill s-{e(f["outcome"])}"></span>{e(f["outcome"])}</td><td>{e(f["note"])}</td>'
    f'<td>{link(f["url"], "comment")} {link(f["reply"], "reply")}</td></tr>' for f in F)
rrows = "".join(
    f'<tr><td>{e(r["date"])}</td><td>{e(r["repo"])}#{r["pr"]}</td><td>{e(r["scope"])}</td>'
    f'<td>{e(", ".join(r["angles"])) or "<em>none</em>"}</td><td>{r["denied"]}</td><td>${r["cost"]:.2f}</td>'
    f'<td><code>{e(r.get("skill_version", ""))}</code></td><td>{e(r["note"])}</td></tr>' for r in R)
legend = "".join(f'<span><i class="pill s-{o}"></i>{o}</span>' for o in OUT)
dates = sorted({x["date"] for x in F + R})

page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>PR review eval</title><style>
:root{{--bg:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--grid:#e1e0d9;--card:#f3f2ee;
--good:#0ca30c;--warn:#fab219;--crit:#d03b3b;--none:#a3a29b}}
@media (prefers-color-scheme:dark){{:root{{--bg:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--grid:#2c2c2a;--card:#232322;--none:#6b6a65}}}}
*{{box-sizing:border-box}}body{{margin:0;padding:24px 16px;background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,sans-serif}}
main{{max-width:1100px;margin:auto}}h1{{font-size:22px;margin:0}}h2{{font-size:15px;margin:32px 0 10px}}
.muted,small{{color:var(--ink2)}}a{{color:inherit}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-top:16px}}
.tile{{background:var(--card);border-radius:8px;padding:12px}}.tile span{{display:block;color:var(--ink2);font-size:12px}}
.tile strong{{font-size:24px;font-variant-numeric:tabular-nums}}.tile small{{display:block}}
.charts{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:24px}}
.legend{{display:flex;gap:14px;font-size:12px;color:var(--ink2);margin-bottom:8px}}
.row{{display:grid;grid-template-columns:96px 1fr 44px;align-items:center;gap:8px;margin:6px 0}}
.row>span{{color:var(--ink2)}}.row b{{font-weight:500;font-variant-numeric:tabular-nums;text-align:right}}
.bar{{display:flex;gap:2px;height:14px}}.bar i{{border-radius:0;min-width:3px}}.bar i:last-child{{border-radius:0 4px 4px 0}}
.bar i:hover{{opacity:.75}}
.s-accepted{{background:var(--good)}}.s-partial{{background:var(--warn)}}.s-declined{{background:var(--crit)}}.s-pending{{background:var(--none)}}
.pill{{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px}}
.scroll{{overflow-x:auto}}table{{border-collapse:collapse;width:100%;font-size:13px}}
th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid var(--grid);vertical-align:top}}
th{{color:var(--ink2);font-weight:500}}td.path{{font-family:ui-monospace,monospace;font-size:12px;word-break:break-all}}
</style></head><body><main>
<h1>PR review eval</h1>
<p class="muted">{dates[0] if dates else "-"} to {dates[-1] if dates else "-"} · generated {datetime.date.today()} ·
acceptance is the author's response, a proxy for precision</p>
<div class="tiles">
{tile("Findings", n, f"{len(set((f['repo'], f['pr']) for f in F))} PRs")}
{tile("Accepted", f"{acc / n * 100:.0f}%" if n else "-", f"{acc} of {n}")}
{tile("Declined", sum(f['outcome'] == 'declined' for f in F))}
{tile("Runs", len(R), f"${sum(r['cost'] for r in R):.2f} total")}
{tile("Runs without subagents", nosub, "skill gate skipped")}
{tile("Denied Bash calls", sum(r['denied'] for r in R))}
</div>
<h2>Outcome by finding</h2><div class="legend">{legend}</div>
<div class="charts"><div><p class="muted">by kind</p>{bars("kind")}</div>
<div><p class="muted">by bucket</p>{bars("bucket")}</div></div>
<h2>Runs by skill version</h2><div class="scroll"><table><tr><th>Version</th><th>Runs</th><th>No subagents</th>
<th>Denied</th><th>Avg cost</th></tr>{vrows}</table></div>
<h2>Findings</h2><div class="scroll"><table><tr><th>Date</th><th>PR</th><th>Where</th><th>Bucket</th><th>Sev</th>
<th>Kind</th><th>Outcome</th><th>Note</th><th></th></tr>{frows}</table></div>
<h2>Runs</h2><div class="scroll"><table><tr><th>Date</th><th>PR</th><th>Scope</th><th>Angles</th><th>Denied</th>
<th>Cost</th><th>Version</th><th>Note</th></tr>{rrows}</table></div>
</main></body></html>"""
(d / "report.html").write_text(page)
print(d / "report.html")
