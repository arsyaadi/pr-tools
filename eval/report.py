#!/usr/bin/env python3
"""Render eval/real-runs/{findings,runs}.jsonl as one offline HTML page (no CDN: the data is private).
usage: eval/report.py [data-dir] [--since YYYY-MM-DD] [--until YYYY-MM-DD] [--version SHA] [--json]
-> <data-dir>/report.html, or the metrics JSON on stdout with --json (no HTML written)"""
import argparse, json, datetime, re
from collections import Counter, defaultdict
from html import escape as e
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("data", nargs="?", default=Path(__file__).parent / "real-runs")
ap.add_argument("--since"); ap.add_argument("--until"); ap.add_argument("--version")
ap.add_argument("--json", action="store_true")
a = ap.parse_args()
d = Path(a.data)
load = lambda n: [json.loads(l) for l in (d / n).read_text().splitlines() if l.strip()] if (d / n).exists() else []

def keep(x):
    return ((not a.since or x["date"] >= a.since) and (not a.until or x["date"] <= a.until)
            and (not a.version or (x.get("skill_version") or "").startswith(a.version)))

F, R = [x for x in load("findings.jsonl") if keep(x)], [x for x in load("runs.jsonl") if keep(x)]
OUT = ["accepted", "partial", "declined", "pending"]  # status colors, always shown with their label
CAUSES = ["missed-rule", "intended", "no-basis", "wrong-reading", "other"]
UNL = "unlabeled"

def prec(fs):
    v, i = sum(f.get("verdict") == "valid" for f in fs), sum(f.get("verdict") == "invalid" for f in fs)
    return {"value": v / (v + i) if v + i else None, "valid": v, "invalid": i}

def group(key):
    g = defaultdict(list)
    for f in F: g[f.get(key) or "-"].append(f)
    return {k: {"n": len(fs), "accepted": sum(f["outcome"] == "accepted" for f in fs),
                "valid": sum(f.get("verdict") == "valid" for f in fs),
                "invalid": sum(f.get("verdict") == "invalid" for f in fs)} for k, fs in g.items()}

def metrics():
    bad = [f for f in F if f.get("verdict") in ("invalid", "debatable")]
    ov = defaultdict(Counter)
    for f in F: ov[f["outcome"]][f.get("verdict") or UNL] += 1
    vs = defaultdict(lambda: {"F": [], "R": []})
    for f in F: vs[f.get("skill_version") or "?"]["F"].append(f)
    for r in R: vs[r.get("skill_version") or "?"]["R"].append(r)
    by_v = {v: {"findings": len(x["F"]), "precision": prec(x["F"]), "runs": len(x["R"]),
                "no_subagents": sum(r["no_subagents"] for r in x["R"]), "denied": sum(r["denied"] for r in x["R"]),
                "avg_cost": sum(r["cost"] for r in x["R"]) / len(x["R"]) if x["R"] else None}
            for v, x in sorted(vs.items())}
    return {
        "filter": {"since": a.since, "until": a.until, "version": a.version},
        "findings": len(F), "prs": len({(f["repo"], f["pr"]) for f in F}),
        "labeled": sum(bool(f.get("verdict")) for f in F),
        "outcomes": dict(Counter(f["outcome"] for f in F)),
        "verdicts": dict(Counter(f.get("verdict") or UNL for f in F)),
        "precision": {"all": prec(F), "non_nit": prec([f for f in F if f["bucket"] != "nit"]),
                      "nit": prec([f for f in F if f["bucket"] == "nit"])},
        "acceptance": sum(f["outcome"] == "accepted" for f in F) / len(F) if F else None,
        "causes": dict(Counter(f.get("cause") or "-" for f in bad)),
        "outcome_vs_verdict": {o: dict(c) for o, c in ov.items()},
        "by_kind": group("kind"), "by_bucket": group("bucket"), "by_version": by_v,
        "runs": {"n": len(R), "cost_total": round(sum(r["cost"] for r in R), 2),
                 "no_subagents": sum(r["no_subagents"] for r in R), "denied": sum(r["denied"] for r in R)},
    }

M = metrics()
if a.json:
    print(json.dumps(M, indent=2)); raise SystemExit

# One source for the glossary section and the hover tooltips. Definitions follow skills/pr-review/SKILL.md
# (scope: step 2b, bucket: steps 4-5, severity: step 4, angles: step 3) and eval/README.md.
GLOSSARY = {
    "Scope": ("which part of the PR a run reviewed", {
        "full": "The whole PR diff: first review, --full, or history rewritten since my last review.",
        "incremental": "Only the commits pushed since my last review.",
        "replies-only": "No new commits: only my earlier threads, re-judged against the author's replies.",
        "none": "Nothing reviewed: skipped (title pattern), stopped (a pending review exists), nothing new, or failed."}),
    "Bucket": ("how a finding was posted", {
        "issue": "Scored 80+ by the scorer: an inline comment.",
        "worth-a-look": "Scored 50-79: posted, labelled lower confidence, with what couldn't be verified.",
        "nit": "Non-blocking smell or test-gap note from angles C and F: not scored, always P3."}),
    "Severity": ("how much it hurts if real, apart from confidence", {
        "P0": "Critical: exploitable security hole, data loss, wrong money or permissions, outage on a main path.",
        "P1": "High: wrong behavior on a common path, or a regression of an earlier fix.",
        "P2": "Medium: bug on an edge path, performance at realistic scale, missing test for changed critical logic.",
        "P3": "Low: everything else worth saying, including all nits."}),
    "Kind": ("what the finding is about", {
        "bug": "Wrong behavior.", "perf": "A performance problem.", "test": "A missing or weak test.",
        "smell": "Code quality or a repo-rule issue.", "doc": "A doc, comment or naming issue."}),
    "Outcome": ("what the author did, from the reply or the next review", {
        "accepted": "Fixed, in this PR or a follow-up PR.", "declined": "Refused, and the code stayed.",
        "partial": "Partly fixed.", "pending": "No reply and no change yet."}),
    "Verdict": ("whether the finding is right, judged by hand against the code", {
        "valid": "Correct, whatever the author did with it.", "invalid": "Wrong.",
        "debatable": "Not clearly right or wrong (e.g. a preference no rule asks for); left out of precision.",
        "unlabeled": "Not judged yet."}),
    "Cause": ("why a finding is invalid or debatable", {
        "missed-rule": "A repo rule allows it, and the review didn't read or apply the rule.",
        "intended": "Deliberate behavior that the PR body or the code makes clear.",
        "no-basis": "No bug and no written rule behind it: a preference.",
        "wrong-reading": "The review misread the code.", "other": "Anything else: the note says what."}),
    "Angle": ("review subagents a run used", {
        "A": "Bugs in the diff (pr-bug-hunter).", "B": "Regressions against git history (pr-bug-hunter).",
        "C": "Repo rules and code smells (pr-quality-hunter).",
        "DE": "Security (D) and performance (E), one call (pr-security-hunter).", "F": "Tests (pr-test-hunter)."}),
    "Metric": ("numbers on this page", {
        "Precision": "valid / (valid + invalid) over labeled findings; debatable left out. The headline number.",
        "Non-nit precision": "Precision over issue and worth-a-look findings.", "Nit precision": "Precision over nits.",
        "Acceptance": "accepted / all findings: the author's response, only a proxy for precision.",
        "No subagents": "Full or incremental runs where no angle subagent ran: the skill's gate was skipped.",
        "Denied": "Bash calls the headless allow list refused; a denied read can leave a check undone.",
        "Version": "pr-tools commit (skill_version). For ingested runs: the last commit before the run, an approximation."}),
}
TIP = {t: x for _, terms in GLOSSARY.values() for t, x in terms.items()}
tip = lambda *ts: (lambda s: f' title="{e(s)}"' if s else "")("\n".join(f"{t}: {TIP[t]}" for t in ts if t in TIP))
gtip = lambda g: tip(*GLOSSARY[g][1])   # a column header: every term of its group

def bars(key):
    """One stacked bar per value of `key`, segments by outcome, widths relative to the largest group."""
    g = defaultdict(Counter)
    for f in F: g[f.get(key) or "-"][f["outcome"]] += 1
    top = max((sum(c.values()) for c in g.values()), default=1)
    rows = []
    for k, c in sorted(g.items(), key=lambda kv: -sum(kv[1].values())):
        n = sum(c.values())
        segs = "".join(f'<i class="s-{o}" style="flex:{c[o]}" title="{e(k)}: {c[o]} {o}"></i>' for o in OUT if c[o])
        rows.append(f'<div class="row"><span{tip(k)}>{e(k)}</span><div class="bar" style="width:{n / top * 100:.1f}%">{segs}</div>'
                    f'<b>{c["accepted"]}/{n}</b></div>')
    return "".join(rows) or '<p class="muted">no data</p>'

def cause_bars():
    c = M["causes"]; top = max(c.values(), default=1)
    return "".join(f'<div class="row"><span{tip(k)}>{e(k)}</span><div class="bar" style="width:{n / top * 100:.1f}%">'
                   f'<i class="s-declined" style="flex:1" title="{e(k)}: {n}"></i></div><b>{n}</b></div>'
                   for k, n in sorted(c.items(), key=lambda kv: -kv[1])) or '<p class="muted">none labeled yet</p>'

def tile(label, value, sub="", term=None):
    return f'<div class="tile"{tip(term or label)}><span>{label}</span><strong>{value}</strong><small>{sub}</small></div>'

def link(u, t): return f'<a href="{e(u)}">{t}</a>' if u else ""
pct = lambda v: f"{v * 100:.0f}%" if v is not None else "-"
cost = lambda v: f"${v:.2f}" if v is not None else "-"
ptile = lambda label, p, sub="", term=None: tile(label, pct(p["value"]), sub or f'{p["valid"]} valid / {p["invalid"]} invalid', term)
tdt = lambda v: f'<td{tip(v)}>{e(v)}</td>'   # a cell whose value is a glossary term

vrows = "".join(
    f'<tr><td><code>{e(v)}</code></td><td>{x["findings"]}</td><td>{pct(x["precision"]["value"])}</td><td>{x["runs"]}</td>'
    f'<td>{x["no_subagents"]}</td><td>{x["denied"]}</td>'
    f'<td>{cost(x["avg_cost"])}</td></tr>' for v, x in M["by_version"].items())
verd = [*sorted({v for c in M["outcome_vs_verdict"].values() for v in c}, key=lambda v: (v == UNL, v))]
ovrows = "".join(f'<tr>{tdt(o)}' + "".join(f'<td>{c.get(v, 0)}</td>' for v in verd) + '</tr>'
                 for o, c in M["outcome_vs_verdict"].items())
ovhead = "".join(f'<th{tip(v)}>{e(v)}</th>' for v in verd)
frows = "".join(
    f'<tr><td>{e(f["date"])}</td><td>{e(f["repo"])}#{f["pr"]}</td><td class="path">{e(f["path"] or "(body)")}{":" + str(f["line"]) if f["line"] else ""}</td>'
    f'{tdt(f["bucket"])}{tdt(f["severity"])}{tdt(f["kind"])}'
    f'<td{tip(f["outcome"])}><span class="pill s-{e(f["outcome"])}"></span>{e(f["outcome"])}</td>'
    f'{tdt(f.get("verdict") or "-")}{tdt(f.get("cause") or "")}<td><code>{e(f.get("skill_version") or "")}</code></td>'
    f'<td>{e(f["note"])}</td><td>{link(f["url"], "comment")} {link(f["reply"], "reply")}</td></tr>'
    for f in sorted(F, key=lambda f: f["date"], reverse=True))   # newest first
rrows = "".join(
    f'<tr><td>{e(r["date"])}</td><td>{e(r["repo"])}#{r["pr"]}</td>{tdt(r["scope"])}'
    f'<td{tip(*r["angles"])}>{e(", ".join(r["angles"])) or "<em>none</em>"}</td><td>{r["denied"]}</td><td>${r["cost"]:.2f}</td>'
    f'<td><code>{e(r.get("skill_version", ""))}</code></td><td>{e(r["note"])}</td></tr>'
    for r in sorted(R, key=lambda r: r.get("run_at") or r["date"], reverse=True))
legend = "".join(f'<span><i class="pill s-{o}"></i>{o}</span>' for o in OUT)
dates = sorted({x["date"] for x in F + R})
ftext = lambda f: " · ".join(f"{k} {v}" for k, v in f.items() if v) or "all time"
flt = ftext(M["filter"])

# Insights are written by /pr-eval and may quote thread text: everything is escaped, only http(s) links become <a>.
INLINE = re.compile(r"`([^`]+)`|\*\*(.+?)\*\*|\[([^\]]+)\]\((https?://[^)\s]+)\)|(https?://[^\s<>)\]]*[^\s<>)\].,;:])")
def inline(s):
    out, i = [], 0
    for m in INLINE.finditer(s):
        c, b, t, u, bare = m.groups()
        out.append(e(s[i:m.start()])); i = m.end()
        out.append(f"<code>{e(c)}</code>" if c is not None else f"<b>{inline(b)}</b>" if b is not None
                   else link(u, e(t)) if u else link(bare, e(bare)))
    return "".join(out) + e(s[i:])

def md(text):
    """The markdown /pr-eval writes: headings, bullets, numbered lists, paragraphs (nested lists flatten)."""
    html, lst = [], None
    for l in text.splitlines():
        m = re.match(r"\s*(?:([-*])|(\d+)\.)\s+(.*)", l)
        kind = ("ul" if m.group(1) else "ol") if m else None
        if lst and kind != lst: html.append(f"</{lst}>"); lst = None
        if m:
            if not lst: html.append(f"<{kind}>"); lst = kind
            html.append(f"<li>{inline(m.group(3))}</li>")
        elif h := re.match(r"#{1,4}\s+(.*)", l): html.append(f"<h3>{inline(h.group(1))}</h3>")
        elif l.strip(): html.append(f"<p>{inline(l)}</p>")
    return "".join(html) + (f"</{lst}>" if lst else "")

insights = ""
if ins := sorted(d.glob("insights-*.md")):
    text = ins[-1].read_text()
    hm = re.match(r"<!--\s*filter:\s*(\{.*?\})\s*-->\n?", text)   # first line, written by /pr-eval step 5
    try: made = json.loads(hm.group(1)) if hm else None
    except ValueError: made = None
    text = text[hm.end():] if hm else text
    if made is None: warn = '<p class="warn">Filter unknown: this file has no filter header.</p>'
    elif made != M["filter"]: warn = (f'<p class="warn">Written for {e(ftext(made))}; this report shows {e(flt)}. '
                                     'Numbers below may not match.</p>')
    else: warn = ""
    insights = (f'<h2>Latest insights</h2><p class="muted">{e(ins[-1].name)}'
                f'{" · " + e(ftext(made)) if made is not None else ""}</p>{warn}<div class="insights">{md(text)}</div>')
# Long tables page client-side, 20 rows at a time; without JS every row shows.
PAGER = """<script>document.querySelectorAll("table.paged").forEach(t => {
  const rows = [...t.rows].slice(1), n = 20, last = Math.ceil(rows.length / n) - 1;
  if (last < 1) return;
  const nav = document.createElement("div"), b = s => nav.appendChild(document.createElement(s));
  nav.className = "pager";
  const prev = b("button"), info = b("span"), next = b("button");
  prev.textContent = "‹ Prev"; next.textContent = "Next ›";
  let p = 0;
  const show = () => {
    rows.forEach((r, i) => r.hidden = i < p * n || i >= (p + 1) * n);
    info.textContent = `${p * n + 1}–${Math.min((p + 1) * n, rows.length)} of ${rows.length}`;
    prev.disabled = p == 0; next.disabled = p == last;
  };
  prev.onclick = () => { p--; show(); }; next.onclick = () => { p++; show(); };
  t.parentNode.after(nav); show();
});</script>"""
prc = M["precision"]
glossary = "".join(f'<h3>{e(g)} <span class="muted">· {e(note)}</span></h3><dl>'
                   + "".join(f"<dt>{e(t)}</dt><dd>{e(x)}</dd>" for t, x in terms.items()) + "</dl>"
                   for g, (note, terms) in GLOSSARY.items())

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
.insights{{background:var(--card);border-radius:8px;padding:2px 16px 10px;overflow-wrap:anywhere}}
.insights h3{{font-size:14px;margin:14px 0 6px}}.insights p{{margin:6px 0}}.insights ul,.insights ol{{margin:4px 0;padding-left:20px}}
.insights li{{margin:3px 0}}code{{font-family:ui-monospace,monospace;font-size:12px}}
.warn{{border-left:3px solid var(--warn);padding:4px 10px;margin:0 0 10px}}
th[title],td[title],.tile[title],.row span[title]{{cursor:help}}
.glossary{{margin-top:32px}}.glossary summary{{cursor:pointer;font-size:15px;font-weight:600}}
.glossary h3{{font-size:13px;margin:18px 0 6px}}.glossary h3 span{{font-weight:400}}
.glossary dl{{display:grid;grid-template-columns:minmax(64px,max-content) 1fr;gap:4px 14px;margin:0}}
.pager{{display:flex;gap:10px;align-items:center;margin-top:8px;font-size:12px;color:var(--ink2)}}
.pager button{{font:inherit;color:var(--ink);background:var(--card);border:1px solid var(--grid);border-radius:6px;padding:3px 10px;cursor:pointer}}
.pager button:disabled{{opacity:.4;cursor:default}}
.glossary dt{{font-family:ui-monospace,monospace;font-size:12px}}.glossary dd{{margin:0;color:var(--ink2)}}
</style></head><body><main>
<h1>PR review eval</h1>
<p class="muted">{flt} · {dates[0] if dates else "-"} to {dates[-1] if dates else "-"} · generated {datetime.date.today()} ·
acceptance is the author's response, a proxy; precision is judged by hand (valid / (valid + invalid)) ·
hover a label for its meaning, or see the <a href="#glossary">glossary</a></p>
{insights}
<div class="tiles">
{ptile("Precision (labeled)", prc["all"], f"{M['labeled']} labeled", "Precision")}
{ptile("Non-nit precision", prc["non_nit"])}
{ptile("Nit precision", prc["nit"])}
{tile("Findings", M["findings"], f"{M['prs']} PRs")}
{tile("Accepted", pct(M["acceptance"]), f"{M['outcomes'].get('accepted', 0)} of {M['findings']}", "Acceptance")}
{tile("Declined", M["outcomes"].get("declined", 0), term="declined")}
{tile("Runs", M["runs"]["n"], f"${M['runs']['cost_total']:.2f} total")}
{tile("Runs without subagents", M["runs"]["no_subagents"], "skill gate skipped", "No subagents")}
{tile("Denied Bash calls", M["runs"]["denied"], term="Denied")}
</div>
<h2>Outcome by finding</h2><div class="legend">{legend}</div>
<div class="charts"><div><p class="muted">by kind</p>{bars("kind")}</div>
<div><p class="muted">by bucket</p>{bars("bucket")}</div></div>
<h2>Invalid / debatable by cause</h2>{cause_bars()}
<h2>Outcome x verdict</h2><div class="scroll"><table><tr><th>Outcome</th>{ovhead}</tr>{ovrows}</table></div>
<h2>By skill version</h2><div class="scroll"><table><tr><th{tip("Version")}>Version</th><th>Findings</th><th{tip("Precision")}>Precision</th><th>Runs</th>
<th{tip("No subagents")}>No subagents</th><th{tip("Denied")}>Denied</th><th>Avg cost</th></tr>{vrows}</table></div>
<h2>Findings</h2><div class="scroll"><table class="paged"><tr><th>Date</th><th>PR</th><th>Where</th><th{gtip("Bucket")}>Bucket</th><th{gtip("Severity")}>Sev</th>
<th{gtip("Kind")}>Kind</th><th{gtip("Outcome")}>Outcome</th><th{gtip("Verdict")}>Verdict</th><th{gtip("Cause")}>Cause</th><th{tip("Version")}>Version</th><th>Note</th><th></th></tr>{frows}</table></div>
<h2>Runs</h2><div class="scroll"><table class="paged"><tr><th>Date</th><th>PR</th><th{gtip("Scope")}>Scope</th><th{gtip("Angle")}>Angles</th><th{tip("Denied")}>Denied</th>
<th>Cost</th><th{tip("Version")}>Version</th><th>Note</th></tr>{rrows}</table></div>
<details class="glossary" id="glossary"><summary>Glossary</summary>{glossary}</details>
</main>{PAGER}</body></html>"""
(d / "report.html").write_text(page)
print(d / "report.html")
