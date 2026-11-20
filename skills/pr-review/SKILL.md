---
name: pr-review
description: Review a GitHub PR for bugs, security and performance problems, repo-rule violations and code smells; findings become inline comments in a PENDING review (only you see it until you submit). Run only when the user invokes it with a PR URL.
argument-hint: "[pr-url] [--headless]"
disable-model-invocation: true
effort: medium
allowed-tools: Task, Agent, Read, Grep, Glob, Bash(gh pr view:*), Bash(gh pr diff:*), Bash(gh repo view:*), Bash(gh api user --jq .login), Bash(pr-threads:*), Bash(git fetch:*), Bash(git blame:*), Bash(git log:*), Bash(git show:*), Bash(git diff:*), Bash(git merge-base:*), Bash(pr-tools-config)
---

Review the pull request given with this skill (its arguments: a PR URL and optional flags) and draft the findings as a **pending** GitHub review.
Adapted from the official `code-review` plugin, with two differences: nothing is published (the
review stays PENDING until I submit it), and findings become inline comments.

Make a todo list first, then follow these steps precisely.

## 1. Load the PR

- Parse the PR URL (`https://github.com/<owner>/<repo>/pull/<n>`) and whether `--headless` was
  passed. `--lean` is accepted and ignored (its pass now always runs, as angle C). No URL → use
  the current branch's PR (`gh pr view --json url --jq .url`); if the branch has no PR, stop and
  say so. `--headless` means nobody is watching: never ask, follow the headless rules below.
- `pr-tools-config` → my settings: `language` (for everything you write on
  GitHub) and `skip_title_regex` (empty = skip nothing).
- `gh api user --jq .login` → my login.
- `gh pr view <url> --json state,isDraft,title,body,author,baseRefName,headRefName,headRefOid,changedFiles,additions,deletions,reviews,url`
- `gh pr diff <url>` → the diff.
- `pr-threads <url>` → the PR's unresolved review threads, anyone's (`path`, `line`, `isOutdated`,
  `comments[]` with `author`, `body`, `url`). Read-only.

## 2. Eligibility (ask, don't guess)

- Closed or merged → stop.
- `skip_title_regex` is set and the title matches it → stop and say why.
- Draft → tell me it's a draft and ask whether to continue.
- I'm the PR's author → **self-review**: `pr-review-post` publishes it right away as a Comment
  (no pending step; GitHub allows nothing else on your own PR). Step 2b applies the same way.
- I already have a PENDING review → stop and tell me to submit or discard it first (menu bar:
  "Submit as …" / "Discard pending review", or on GitHub); GitHub allows only one pending review per
  user per PR.
- `--headless`: don't ask. Drafts → continue. Closed/merged, skipped titles and an existing PENDING
  review → stop with a `STATUS:` line (step 8).

## 2b. Scope: full or incremental

GitHub records which commit each review was made on (`reviews[].commit.oid`). Take my latest
submitted review on this PR (author = my login, state not PENDING); that commit is `LAST`.

- No previous review → **full review** of the PR diff.
- `LAST` == `headRefOid` → nothing new since my last review: stop (headless:
  `STATUS: nothing new since your last review`).
- Otherwise, when the current directory is a clone of the PR's repo: `git fetch origin pull/<n>/head --quiet`,
  then `git merge-base --is-ancestor LAST <headRefOid>`.
  - Ancestor → **incremental review**: the diff to review is `git diff LAST <headRefOid>` (only the new
    commits). Tell me how many commits are new; don't ask. The summary still covers the whole
    PR for context, but agents review only the incremental diff.
  - Not an ancestor (rebased / force-pushed) → full review, and say why.
- Not in a clone → full review, and say why.

In incremental mode, the review `body` opens with `Incremental review: <k> new commits since
<LAST short sha>.` (in `language`). Inline comments must still sit on lines inside the PR's full diff (`gh pr diff`);
anything else goes in the body.

## 2c. My open threads

My unresolved threads are the ones from `pr-threads` whose first comment is mine. For each, read
the code it points at on `headRefOid` (`git show <headRefOid>:<path>` in a clone, after
`git fetch origin pull/<n>/head --quiet` if step 2b didn't run it; else the diff)
and decide: **addressed** (the code no longer has the problem), **open** (unchanged or only partly
fixed), or **unclear**. Say why in one line each. Don't reply to or resolve the threads: there is no
write path for that, and resolving is mine.

When there is at least one, the review `body` gets a section `**My earlier comments**` (in
`language`): `<n> addressed, <m> still open`, then one bullet per open or unclear thread with its
first comment's `url` and the one-line reason. Addressed threads are only counted. Open threads
are not raised again as new findings.

## 3. Review with parallel agents

Split the diff first: pure renames/moves (`rename from/to` with no hunks, or `similarity index 100%`)
carry no code to review. List them by name only and leave them out of what the agents read.

Summarize the change first (what and why, from title, body and the non-rename diff; a small, fast
subagent on a cheaper model is enough, if your agent lets you pick one). Pass that summary to all angles below and to the scorer, so intentional
changes aren't flagged. Also pass all unresolved threads (path, line, first comment's body) as
**already raised**: the angles don't report them again.

In a clone of the PR's repo (`gh repo view --json nameWithOwner` matches `<owner>/<repo>`), run
`git fetch origin <baseRefName> --quiet` now: B and C both read `origin/<baseRefName>`.

Then review from four angles: A and B look for bugs, C for code quality, D for security and
performance. Run all four on every review, however small the diff; no shortcut, no "I checked it
myself instead". If you can run subagents, you must run them as four subagents **in parallel** (in
Claude Code: `pr-bug-hunter` for A and B, `pr-quality-hunter` for C, which gets angle C below and
`quality-checklist.md` verbatim, `pr-security-hunter` for D, which gets angle D below and
`security-perf-checklist.md` verbatim); only an agent that can't run subagents does A, then B, then
C, then D itself, and reads `quality-checklist.md` before C and `security-perf-checklist.md`
before D. Each angle yields a list of issues: file, line(s) on the new side, description, and the
reason it was flagged. Your final output names the angles that ran (and how C
was grouped), and any that were skipped with the reason.

Large PRs dilute angle C. When the non-rename diff touches more than 10 files or 800 changed lines,
split C into groups of at most ~10 files, by directory or feature (keep a composable with the
components and pages that use it), and run one C subagent per group in parallel. Each gets its
group's diff plus the PR's full file list; the smell cap applies per group.

- **A: bugs in the diff.** Read only the changed code and do a shallow scan for real bugs:
  wrong logic, broken edge cases, null/undefined handling, wrong API usage, data loss, security
  holes introduced by this change. Focus on large issues and skip nitpicks.
- **B: history context.** Only in a clone of the PR's repo; otherwise skip it and say so.
  Use `git log` / `git blame origin/<baseRefName>` on the modified regions to find bugs that the
  history makes visible, e.g. reverting a previous fix or breaking an invariant other code relies on.
- **C: code quality.** Only code this PR adds or makes worse; skip pre-existing problems, generated
  code, and anything a linter/formatter/typechecker already fails on in CI.
  1. **Repo rules.** Only in a clone of the PR's repo (otherwise skip this part and say so). Read
     the rules from the base branch with `git show origin/<baseRefName>:<path>`, so the PR can't
     rewrite its own rules: `CLAUDE.md`, `AGENTS.md`, `CONTRIBUTING.md`,
     `.github/copilot-instructions.md` (whichever exist), plus the docs they import (`@file`) or
     link to that cover the code this PR touches (general code rules, and the doc for each layer
     changed). Check every applicable rule against every changed line, including placement rules
     ("where code goes"): each new constant, helper, type, fetch or toast sits in the layer or
     folder the rules assign (e.g. a status code defined locally in a component when the rules
     put fixed values in a constants folder). Their thresholds and conventions override the
     defaults in the checklist.
  2. **General checklist:** `quality-checklist.md` in this skill's folder (read it; pass it
     verbatim to the subagent). Every item is tagged `[must]` (an objective breach) or `[nit]`.
     Also apply the must-follow rules of the official style guide of the language and framework in
     use, where a linter wouldn't already catch them.

  Review every changed line. Each finding: file, line(s), a one-line description, a concrete one-line
  fix, and its source. A **rule** finding is backed by a written repo rule (quote it, give its
  file) or a `[must]` item (quote the item, plus the measured value, e.g. the complexity score, or
  the other copy's location). No cap on those. The rest are **smells**: at most 15, most impactful
  first.
- **D: security and performance.** Check every changed line against `security-perf-checklist.md`
  in this skill's folder (read it; pass it verbatim to the subagent): injection, XSS, broken access
  control, CSRF, secrets, unsafe deserialization, path traversal, SSRF, weak crypto, mass assignment;
  N+1 queries, unbounded work, quadratic hot paths, missing indexes, repeated work, resource leaks,
  blocking calls. Each finding: file, line(s), `security` or `performance`, the checklist item, a
  one-line description, the evidence (the untrusted input's path to the sink, or what grows with
  input), and a concrete one-line fix. No evidence, no finding. In a clone, look for the repo's own
  guard, helper or index before flagging; outside one, judge from the diff and say so.

Bugs come from A, B and D: C doesn't report bugs, and A/B/D don't report style. D reports only
security and performance; A may still catch an obvious security hole, and the scorer merges the
two.

**Gate before step 4.** In Claude Code, check that you have called the `Task`/`Agent` tool with
`pr-bug-hunter` for A, `pr-bug-hunter` for B (unless B was skipped for no clone),
`pr-quality-hunter` for C (once per group), and `pr-security-hunter` for D, and have their
results. If any is missing, call it now. Reading the diff yourself doesn't replace them, even for
a one-line change.

## 4. Score and filter

Score all issues from A, B and D and the rule findings from C together in **one** fresh subagent if you can (a smaller, cheaper model is fine); a
fresh context judges more honestly than the one that found the issues. Otherwise score them yourself,
skeptically. Give it the summary, the non-rename diff inline (so it doesn't re-fetch anything) and the
numbered issue list; it scores each issue's confidence 0-100 that it is real (this rubric verbatim):

- 0: false positive that doesn't survive light scrutiny, or a pre-existing issue.
- 25: might be real, couldn't verify.
- 50: verified real, but a nitpick or rare in practice.
- 75: double-checked, very likely hit in practice, directly impacts functionality.
- 100: certain, confirmed by the evidence, will happen frequently.

Before scoring, merge issues that two angles report on the same line for the same cause into one.
A D finding is scored on this rubric too, against its evidence: if the input isn't really
untrusted, an existing guard already stops it, or the data is bounded, it's 25 at most.

For a rule finding, score instead whether the quoted rule (or `[must]` item) really says that and
covers this line, and whether the measured value holds when you check it: 100 if it names this case
outright, 75 if it clearly applies, 25 if it's a stretch, 0 if the rule isn't there or the
measurement is wrong. Give the scorer the rule files' text and `quality-checklist.md` for that.

Buckets: **≥ 80** → inline comments; **50-79** → "worth a look" inline comments (labelled as lower
confidence); **< 50** → drop. Also drop, whatever the score: anything an unresolved thread already raises on the same line or
range (give the scorer the already-raised list for this), pre-existing issues, issues on lines this PR didn't touch,
things a linter/typechecker/CI would catch, pedantic style that no written repo rule asks for, and
intentional behavior changes that are part of the PR's purpose. Don't build or run tests.

## 5. Nits

Smells from angle C go in a separate group labelled `nit (non-blocking)`. They are not scored and
never block the merge. Drop a nit that sits on the same line as a scored finding, or that
contradicts the summary's stated intent.

## 6. Show me before posting

Print a numbered list of everything that survived: `file:line`, one-line description, score and
bucket (inline / worth a look / nit), and the rule file for rule findings. If nothing scored ≥ 50, there are no nits and none of my earlier comments (step 2c) is open or unclear:
- someone else's PR → skip the question and go to step 7 with no comments, only a `body` of
  `LGTM. No issues found (checked for bugs, regressions against history, security, performance, repo rules and code smells).` (in `language`).
  It stays pending, so I can submit it as Approve in one click.
- self-review → same, with `body` `LGTM (self-review). No issues found (checked for bugs,
  regressions against history, security, performance, repo rules and code smells).` It is published right away as a Comment.
Ask which ones to drop, then wait for my answer. With `--headless`, don't ask: keep everything
(I curate the pending review on GitHub).

## 7. Draft the pending review

Write each kept finding in this shape. No emojis, no filler, one short sentence per line:

```
**<title: what is wrong, one line>**

- **Impact:** <what breaks, and when>
- **Fix:** <the fix in one line; code in backticks>
```

Add a `- **Why:**` bullet between them only when the cause isn't obvious from the title. A rule
finding uses `- **Rule:** <file>: <the rule, quoted or tightly paraphrased>` in place of `Impact`
(for a `[must]` item: `- **Rule:** <the item>` plus the measured value, e.g. `cognitive complexity 22 > 15`).
Nits: `nit (non-blocking): <one line>`, plus a `- **Fix:**` bullet if the fix isn't obvious.

**Language:** write the review (comments and body) in `language` from my settings, whatever
language the PR uses. Keep technical terms, code identifiers, file paths and error messages in
English as they are (e.g. "race condition", "null check", `formatDateTime`); don't translate them.
The fixed phrases (including the `Impact` / `Why` / `Fix` labels) are given in English: write
them in `language` too. Footers stay as given, with `<agent>` replaced by the link for the agent
you are: `[Claude Code](https://claude.com/claude-code)`, `[Codex](https://openai.com/codex)` or
`[Antigravity](https://antigravity.google)`.

- A finding whose line is on the new (RIGHT) side of a diff hunk → an inline comment
  `{"path", "line", "side": "RIGHT", "body"}`. For multi-line ranges add `start_line` and
  `start_side: "RIGHT"`.
- A finding outside the diff hunks → a bullet in the review `body`, linked as
  `https://github.com/<owner>/<repo>/blob/<headRefOid>/<path>#L<a>-L<b>` (full sha).
- `body` opens with one line: how many issues were found and that bugs were checked, e.g.
  `Found 2 issues and 1 nit (checked for bugs, regressions against history, security, performance, repo rules and code smells).`
- "Worth a look" findings (50-79) are inline comments too (same placement rules), starting with
  `**Worth a look (lower confidence):**` in front of the title. Only ones outside the diff hunks go in the `body`,
  under a `**Worth a look (lower confidence)**` heading with a permalink each.
- `body` always ends with a blank line and then exactly this footer (also on LGTM reviews):
  `🤖 Reviewed with <agent>`.
- Every inline comment ends with a blank line and then exactly:
  `<sub>🤖 Reviewed with <agent></sub>`.

Create the review with `pr-review-post`, the only allowed write path. It takes
`{"commit_id": "<headRefOid>", "body": "...", "comments": [...]}` on stdin, strips `event` so the
review stays PENDING, and refuses any PR other than the one being reviewed. `commit_id` is the
`headRefOid` from step 1 (its first 7+ characters are enough). If the PR got new commits since, the
script refuses (exit 5), because the lines may have moved: don't retry with the new head, stop and
tell me to review again (headless: `STATUS: failed, new commits during the review, run it again`).

```
pr-review-post <pr-url> <<'JSON'
{...}
JSON
```

Claude Code: skip the heredoc, its bash check blocks a JSON body inline ("brace with quote
character"). Write the JSON with the Write tool to the review draft file the prompt names (headless
runs may write nowhere else), or to a file of your choice if it names none, then run
`pr-review-post <pr-url> < <that file>`.

Don't call `gh api` to write anything yourself. If it fails with 422 because a line can't be
resolved, move those comments into `body` and retry once. Submitting is mine to do.

## 8. Hand over

Print the number of inline comments and body notes, plus `<pr-url>/files`. Remind me the review is
pending: I finish it on GitHub with "Finish your review" → Comment / Approve / Request changes.
GitHub's "Finish your review" box drops the drafted `body`, so tell me to submit with the pr-tools
menu bar ("Submit as …") or by running this myself in a terminal, which keeps it (never run it
yourself): `pr-review-submit <pr-url> APPROVE|COMMENT|REQUEST_CHANGES`.
For a self-review there is nothing to finish: it's already published as a Comment.

With `--headless`, the **last line** of your output must be one line starting with `STATUS: `
(it becomes the notification), e.g. `STATUS: pending review drafted, 2 inline + 1 worth a look + 3 nits`, `STATUS: self-review posted, 1 inline`,
`STATUS: no issues, LGTM drafted (pending)`, `STATUS: pending review drafted, 1 inline, 2 of 3 earlier comments addressed`, `STATUS: skipped, title matches the skip pattern`, `STATUS: stopped, you already have a
pending review`, `STATUS: failed, <short reason>`.
