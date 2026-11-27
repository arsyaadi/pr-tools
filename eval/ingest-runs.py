#!/usr/bin/env python3
"""Append headless Claude runs from the cache to eval/real-runs/runs.jsonl.
usage: eval/ingest-runs.py [--cache DIR] [--data DIR] [--dry-run]
Each PR's log is overwritten by its next run and cache files older than 30 days are deleted
(bin/pr-review-headless), so run this regularly."""
import argparse, datetime, json, re, subprocess
from pathlib import Path

root = Path(__file__).resolve().parent.parent
ap = argparse.ArgumentParser()
ap.add_argument("--cache", default=Path.home() / ".cache/pr-review")
ap.add_argument("--data", default=root / "eval/real-runs")
ap.add_argument("--dry-run", action="store_true")
a = ap.parse_args()
cache, data = Path(a.cache), Path(a.data)
runs_f = data / "runs.jsonl"
old = [json.loads(l) for l in runs_f.read_text().splitlines() if l.strip()] if runs_f.exists() else []

AGENTS = {"pr-quality-hunter": "C", "pr-security-hunter": "DE", "pr-test-hunter": "F"}
ORDER = ["A", "B", "C", "DE", "F"]

def parse(path):
    """-> (result event, set of angles) or None when the log has no result event (not a Claude run)."""
    res, angles = None, set()
    for l in path.read_text(errors="replace").splitlines():
        try: ev = json.loads(l)
        except ValueError: continue
        if not isinstance(ev, dict): continue
        if ev.get("type") == "result": res = ev
        blocks = (ev.get("message") or {}).get("content") if ev.get("type") == "assistant" else None
        for b in blocks if isinstance(blocks, list) else []:
            if not (isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") in ("Task", "Agent")): continue
            i, t = b.get("input") or {}, b.get("input", {}).get("subagent_type")
            if t in AGENTS: angles.add(AGENTS[t])
            elif t == "pr-bug-hunter":
                desc = i.get("description") or ""
                ab = [x for x, rx in (("A", r"\bA\b|bug"), ("B", r"\bB\b|history")) if re.search(rx, desc, re.I)]
                angles.update(ab or ["A"])
    return (res, angles) if res else None

def scope(text, body, status):
    """body = the drafted review's body: it opens with `Re-review:` / `Incremental review:` (pr-review step 2b)."""
    s, b = (status or "").lower(), body.lstrip().lower()
    if re.match(r"(skipped|stopped|nothing|failed)", s): return "none"
    if b.startswith("re-review") or s.startswith("replies checked"): return "replies-only"
    if b.startswith("incremental review") or re.search(r"incremental review", text, re.I): return "incremental"
    return "full"

def version(at):
    # approximation: assumes the installed skill is this clone as of that time
    return subprocess.run(["git", "-C", str(root), "log", "-1", "--format=%h", f"--before={at}"],
                          capture_output=True, text=True).stdout.strip()

new, non_claude, skipped = [], 0, 0
for p in sorted(cache.glob("*.jsonl")):
    repo, _, pr = p.stem.rpartition("-")
    if not repo or not pr.isdigit(): continue
    got = parse(p)
    if not got: non_claude += 1; continue
    res, angles = got
    run_at = datetime.datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")
    denials = res.get("permission_denials") or []
    text = res.get("result") or ""
    st = [l[8:].strip() for l in text.splitlines() if l.startswith("STATUS: ")]
    rv = p.with_suffix(".review.json")   # removed before each run, so it's this run's draft or absent
    try: body = json.loads(rv.read_text()).get("body") or "" if rv.exists() else ""
    except (ValueError, AttributeError): body = ""
    sc = scope(text, body, st[-1] if st else None)
    row = {"date": run_at[:10], "repo": repo, "pr": int(pr), "scope": sc,
           # only a review that should have run angles counts; skipped and replies-only runs run none by design
           "angles": [x for x in ORDER if x in angles], "no_subagents": not angles and sc in ("full", "incremental"),
           "cost": round(res.get("total_cost_usd") or 0, 2), "denied": len(denials),
           "skill_version": version(run_at), "note": "", "run_at": run_at, "status": st[-1] if st else None,
           "denied_cmds": [(x.get("tool_input") or {}).get("command") or json.dumps(x.get("tool_input")) for x in denials]}
    dup = any((o["repo"], o["pr"]) == (repo, int(pr)) and
              (o["run_at"] == run_at if o.get("run_at") else (o["date"], o["cost"]) == (row["date"], row["cost"]))
              for o in old)
    if dup: skipped += 1
    else: new.append(row)

if new and not a.dry_run:
    data.mkdir(parents=True, exist_ok=True)
    with runs_f.open("a") as f:
        for r in new: f.write(json.dumps(r) + "\n")
for r in new: print(("would add " if a.dry_run else "added ") + f'{r["repo"]}#{r["pr"]} {r["run_at"]} {r["scope"]} {r["angles"]} ${r["cost"]}')
print(f'{"would add" if a.dry_run else "added"} {len(new)}, skipped {skipped} existing, {non_claude} non-Claude')
print("note: each PR's log is overwritten on its next run and cache files older than 30 days are deleted; run this regularly")
