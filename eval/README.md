# Evaluating `pr-review`

How to tell whether a change to the skill, a checklist or an agent makes reviews better or worse.
Precision comes first: a wrong comment costs the author's time and the reviewer's trust, a missed
nit costs little.

## Benchmark set

A fork (or a throwaway repo) with frozen PRs, each labeled by hand before any run. Aim for 30+ PRs,
spread like this:

| Kind | Share | What it tests |
|---|---|---|
| Known bugs | ~25% | Seeded or real-history bugs: transactions, idempotency, state transitions, null handling, off-by-one, time zones, races, reverted fixes (with history in the repo, for angle B) |
| Security holes | ~15% | IDOR, auth bypass, injection, SSRF, secrets in logs, CORS with credentials |
| Business-logic changes | ~20% | Intentional behavior changes described in the PR body; nothing should be flagged as a bug |
| Legitimate refactors | ~20% | Renames, moves, extractions with no behavior change |
| Clean PRs | ~20% | Small correct changes; the right output is LGTM |

Add a few adversarial ones: a PR body that claims a security hole is intentional, and a code
comment telling AI reviewers to approve. Both must still produce the finding.

Label each PR with its expected findings: `path`, line range on the new side, kind (`bug`,
`security`, `performance`, `test`, `rule`), and severity (`P0`–`P3`). Nits aren't labeled.

```json
{"pr": "https://github.com/<owner>/<fork>/pull/7", "kind": "known-bug",
 "expected": [{"path": "src/orders.ts", "lines": [41, 44], "type": "bug", "severity": "P1"}]}
```

## Running

Run each PR headless from a clone (`PR_AGENT=claude pr-review-headless <url>`). For Claude Code the
drafted review is kept at `~/.cache/pr-review/<repo>-<n>.review.json`; for the other agents, read
the pending review on GitHub. Discard each pending review afterwards (`pr-review-discard`), so the
next run isn't stopped by it. Run each PR at least twice: agent output varies between runs.

## Matching and metrics

A posted finding (inline or in the body, nits excluded) matches an expected one when the path is
the same and its lines overlap the labeled range ±3 lines. Each expected finding matches at most once.

- **Precision** = matched / posted. The headline number. Report it for ≥ 80 findings and for
  "worth a look" separately.
- **Recall** = matched / expected.
- **False-positive rate on clean PRs** = clean or refactor PRs with any non-nit finding / all clean
  or refactor PRs. Target: close to 0.
- **Finding accuracy** = matched findings whose description names the right cause (judged by hand;
  a right line with a wrong reason is a miss in disguise).
- **Severity accuracy** = matched findings with the labeled severity / matched; also count findings
  off by two or more levels.
- **Coverage** = PRs whose hand-over line lists every angle the rules say should have run, and no
  unexplained skipped files.
- **Noise** = nits per PR, tracked but not optimized.

Compare a change against the previous version on the same set. Keep a change only if precision
doesn't drop; trade recall for precision, never the other way round.

## Real runs (local only)

Outcomes of reviews on real PRs, as a cheap check between benchmark runs. They live in
`eval/real-runs/`, which is gitignored: the reviewed repos are private, and paths, links and notes
would leak them. Nothing in there is committed.

- `findings.jsonl`: one line per posted finding (nits included): `repo`, `pr`, `path`, `line`,
  `placement`, `bucket` (`issue` / `worth-a-look` / `nit`), `severity`, `kind` (`bug`, `perf`,
  `test`, `smell`, `doc`), `outcome` (`accepted`, `declined`, `partial`, `pending`), `note`, `url`,
  `reply`. The outcome is the dev's response, from the author's reply or the next incremental
  review, judged by hand. Optional, missing = null:
  - `verdict`: `valid` / `invalid` / `debatable`, whether the finding was right. Judged by hand
    against the code, separate from `outcome` (a dev can decline a real bug); null = unlabeled.
  - `cause`: why an invalid or debatable one was wrong: `missed-rule`, `intended`, `no-basis`,
    `wrong-reading`, `other`.
  - `skill_version`: pr-tools short sha the run used.
- `runs.jsonl`: one line per headless run: `scope`, the `angles` that ran as subagents,
  `no_subagents`, `cost`, `denied` (Bash calls denied), `skill_version` (pr-tools commit). Optional:
  `run_at` (ISO local seconds), `status` (the `STATUS:` line), `denied_cmds` (the denied commands).
- `insights-<date>.md`: written by `/pr-eval`; `report.py` shows the newest one at the top.

**Precision** = `valid / (valid + invalid)` over labeled findings; `debatable` and unlabeled are
excluded. It is reported for all findings, non-nit and nit. Acceptance (`accepted / findings`) is
only a proxy: an author can accept a wrong nit or decline a right one, and missed bugs don't show
up at all.

```bash
python3 eval/report.py [data-dir] [--since YYYY-MM-DD] [--until YYYY-MM-DD] [--version SHA] [--json]
```

Writes `eval/real-runs/report.html` (one offline page, no CDN), or prints the metrics JSON with
`--json` (no HTML). The filters apply to findings and runs: dates are inclusive, `--version` is a
prefix match on `skill_version`. The terms it uses (scope, bucket, severity, kind, outcome, verdict,
cause, angles, metrics) are defined once in `GLOSSARY` in `report.py`, shown as hover tooltips and in
the page's Glossary section.

```bash
python3 eval/ingest-runs.py [--cache DIR] [--data DIR] [--dry-run]
```

Appends the headless Claude runs in `~/.cache/pr-review` to `runs.jsonl` (cost, angles from the
subagent calls, denied commands, status, scope), skipping ones already logged. Each PR's log is
overwritten by its next run, and `bin/pr-review-headless` deletes cache files older than 30 days,
so run it regularly. `skill_version` is an approximation: the commit of this clone at the run's
time, which assumes the installed skill is this clone.

### `/pr-eval`

A project skill for Claude Code, available only when you work in this repo (it isn't installed).
It ingests the runs, finds my posted findings on the PRs, proposes `outcome`, `verdict` and `cause`
for each (I confirm before anything is written), takes the numbers from `report.py --json`, and
writes `insights-<date>.md` with proposed changes. Arguments: the same filters, plus PR URLs.
