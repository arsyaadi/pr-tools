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
