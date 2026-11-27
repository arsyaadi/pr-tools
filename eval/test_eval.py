#!/usr/bin/env python3
"""python3 eval/test_eval.py: checks report.py and ingest-runs.py on temp dirs only."""
import json, subprocess, sys, tempfile
from pathlib import Path

here = Path(__file__).parent
run = lambda script, *args: subprocess.run([sys.executable, str(here / script), *args], capture_output=True, text=True, check=True).stdout
jl = lambda path, rows: path.write_text("".join(json.dumps(r) + "\n" for r in rows))

def finding(date, bucket, verdict=None, v="aaa1111", **kw):
    return {"date": date, "repo": "r", "pr": 1, "path": None, "line": None, "placement": "inline", "bucket": bucket,
            "severity": "P2", "kind": "bug", "outcome": "accepted", "note": "", "url": "", "reply": "",
            "verdict": verdict, "skill_version": v, **kw}

# report: precision math, filters, empty data
with tempfile.TemporaryDirectory() as t:
    d = Path(t)
    jl(d / "findings.jsonl", [
        finding("2026-11-01", "issue", "valid"), finding("2026-11-01", "issue", "invalid", cause="intended"),
        finding("2026-11-02", "issue", "debatable", cause="no-basis"), finding("2026-11-02", "nit", "valid"),
        finding("2026-11-03", "nit", "invalid", v="bbb2222", cause="other"), finding("2026-11-03", "nit"),
        {k: v for k, v in finding("2026-11-03", "issue").items() if k not in ("verdict", "skill_version")}])
    jl(d / "runs.jsonl", [{"date": "2026-11-01", "repo": "r", "pr": 1, "scope": "full", "angles": [], "no_subagents": True,
                           "cost": 0.5, "denied": 1, "skill_version": "aaa1111", "note": ""}])
    m = json.loads(run("report.py", str(d), "--json"))
    assert m["findings"] == 7 and m["labeled"] == 5 and m["verdicts"]["unlabeled"] == 2
    assert m["precision"]["all"] == {"value": 0.5, "valid": 2, "invalid": 2}  # debatable excluded
    assert m["precision"]["non_nit"]["value"] == 0.5 and m["precision"]["nit"]["value"] == 0.5
    assert m["causes"] == {"intended": 1, "no-basis": 1, "other": 1}
    assert json.loads(run("report.py", str(d), "--json", "--since", "2026-11-03"))["findings"] == 3
    assert json.loads(run("report.py", str(d), "--json", "--until", "2026-11-01"))["findings"] == 2
    x = json.loads(run("report.py", str(d), "--json", "--version", "bbb"))
    assert x["findings"] == 1 and x["runs"]["n"] == 0
    assert json.loads(run("report.py", str(d), "--json", "--version", "aaa"))["runs"]["n"] == 1
    assert "report.html" in run("report.py", str(d)) and (d / "report.html").exists()
    run("report.py", str(d), "--since", "2030-01-01")  # empty filter result
    # insights: rendered markdown, escaped, only http(s) links, filter header compared with the report's
    (d / "insights-2026-11-01.md").write_text("old")
    (d / "insights-2026-11-02.md").write_text(
        '<!-- filter: {"since": "2026-11-03", "until": null, "version": null} -->\n## Head\n'
        "- **[P2] `a<b`** see https://github.com/o/r/pull/1.\n- [bad](javascript:alert(1)) <script>x</script>\n1. one\n")
    run("report.py", str(d), "--since", "2026-11-03")
    h = (d / "report.html").read_text()
    assert "insights-2026-11-02.md" in h and "<h3>Head</h3>" in h and "<ul><li><b>[P2] <code>a&lt;b</code></b>" in h, h
    assert '<a href="https://github.com/o/r/pull/1">https://github.com/o/r/pull/1</a>.' in h
    assert "<script>x" not in h and 'href="javascript' not in h and "<ol><li>one</li></ol>" in h
    assert "Written for" not in h and "filter:" not in h
    run("report.py", str(d))
    h = (d / "report.html").read_text()
    assert "Written for since 2026-11-03; this report shows all time" in h
    # glossary: section present, cells and headers carry tooltips from the same dict
    assert '<details class="glossary" id="glossary">' in h and "<dt>worth-a-look</dt>" in h
    assert '<td title="no-basis: No bug and no written rule behind it: a preference.">no-basis</td>' in h
    assert '<th title="issue: Scored 80+' in h
    assert h.count('<table class="paged">') == 2 and 'querySelectorAll("table.paged")' in h  # findings + runs
    ft = h.split("<h2>Findings</h2>")[1].split("</table>")[0]
    assert ft.index("2026-11-03") < ft.index("2026-11-01")  # newest first
with tempfile.TemporaryDirectory() as t:
    assert json.loads(run("report.py", t, "--json"))["precision"]["all"]["value"] is None
    run("report.py", t)

# ingest-runs: Claude log parsed, non-Claude skipped, rerun adds nothing
def use(name, desc, st="pr-bug-hunter"):
    return {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name, "input": {"subagent_type": st, "description": desc}}]}}
with tempfile.TemporaryDirectory() as c, tempfile.TemporaryDirectory() as d:
    cache = Path(c)
    jl(cache / "my-repo-7.jsonl", [
        use("Task", "Angle B history"), use("Agent", "Angle C quality", "pr-quality-hunter"),
        use("Task", "Angle F tests", "pr-test-hunter"), {"type": "assistant", "message": {"content": "text"}},
        {"type": "result", "total_cost_usd": 0.456, "permission_denials": [{"tool_input": {"command": "rm x"}}],
         "result": "done, checked the replies\nSTATUS: pending review drafted, 1 inline"}])
    (cache / "my-repo-7.review.json").write_text(json.dumps({"body": "Incremental review: 1 new commit since abc1234."}))
    # skipped run: no angles by design, so not a gate skip
    jl(cache / "my-repo-9.jsonl", [{"type": "result", "total_cost_usd": 0.1, "result": "STATUS: nothing new since your last review"}])
    jl(cache / "other-8.jsonl", [{"type": "message", "text": "codex"}])
    (cache / "nopr-x.jsonl").write_text("{}\n")
    out = run("ingest-runs.py", "--cache", c, "--data", d)
    assert "added 2, skipped 0 existing, 1 non-Claude" in out, out
    r, s = [json.loads(l) for l in (Path(d) / "runs.jsonl").read_text().splitlines()]
    assert (r["repo"], r["pr"], r["angles"], r["no_subagents"]) == ("my-repo", 7, ["B", "C", "F"], False)
    assert (r["cost"], r["denied"], r["denied_cmds"], r["scope"]) == (0.46, 1, ["rm x"], "incremental"), r
    assert r["status"] == "pending review drafted, 1 inline" and r["run_at"][:10] == r["date"]
    assert (s["pr"], s["scope"], s["angles"], s["no_subagents"]) == (9, "none", [], False), s
    assert "added 0, skipped 2 existing" in run("ingest-runs.py", "--cache", c, "--data", d)
    assert len((Path(d) / "runs.jsonl").read_text().splitlines()) == 2
print("ok")
