---
name: pr-fix
description: Fix unresolved review comments on your own PR as uncommitted changes (nothing is committed, pushed or replied). Run only when the user invokes it with a PR URL.
argument-hint: "<pr-url> --notes <path> [--headless]"
disable-model-invocation: true
effort: medium
allowed-tools: Task, Agent, Bash(pr-threads:*), Bash(pr-tools-config), Bash(git status:*), Bash(git diff:*), Bash(git log:*), Bash(git show:*), Bash(git blame:*)
---

Address the unresolved review comments on the pull request given with this skill (its arguments). You only edit files in
the current directory (a checkout of the PR branch). You never commit, push or reply on GitHub:
I review your changes in my editor, and `pr-fix-finish` commits/pushes and replies afterwards.

## 1. Load

- Parse the PR URL, the `--notes <path>` file path, and whether `--headless` was passed
  (`--headless`: nobody is watching, never ask).
- `pr-tools-config` → my settings; `language` is for the replies you draft.
- `pr-threads <url>` → PR info and the unresolved threads (id, path, line,
  isOutdated, comments). Stop if the PR isn't mine (`mine: false`) or has no unresolved threads.
- `git log -1 --format=%H` must equal `headRefOid`; if not, stop and say the checkout is stale.

## 2. Triage each thread

Read the whole thread (later comments can change the ask) and the code around `path:line`.

Before acting on a suggestion, check that it's right: read the code it touches and its callers
(`git log` / `git blame` when the history explains why it's written that way). Reviewers can be
wrong: a null check on a value that can't be null, a rename that collides, a "simplification" that
drops an edge case, advice that contradicts a repo rule. If applying it would be wrong or break
something, don't apply it: make the thread a **question** whose reply says what you found, with the
evidence (file:line, the caller, the commit). If it's right but there is a simpler way to the same
result, apply that and say so in the reply.

- **fix**: a concrete, local change the reviewer asked for (rename, null check, missing case, move
  code, typo, small refactor). Make the smallest change that satisfies it, in the repo's style. Don't
  touch unrelated code and don't reformat files.
- **question**: the reviewer asks why/what, or wants discussion. Don't change code; draft an answer
  from the code and history.
- **skip**: I should decide: disagreement, product/behavior decisions, large redesigns, unclear asks,
  or outdated threads whose code no longer exists. Say why.

Don't build or run tests (only read-only git is allowed). If a fix needs a follow-up you can't verify,
say so in its reply.

## 3. Self-check the fixes

Skip this when no file changed. Otherwise review your own change before handing it over: the
uncommitted diff (`git diff`) against the threads you fixed. If you can run subagents, run one
`pr-bug-hunter` (Claude Code) with the PR URL, base branch, angle "bugs in the diff", that diff and
each fix thread's `path:line` and ask; otherwise check it yourself, skeptically, as a reviewer who
didn't write it. Look only at what your change broke: wrong logic, a missed case or another caller
of the code you changed, a fix that doesn't fully do what the thread asked.

For each real problem: correct it with the smallest change, or undo that thread's change and make
it a **skip** with the reason. Don't run the check a second time. Your final output says whether the
self-check ran, as a subagent or by you, and what it changed.

## 4. Write the notes file

Write JSON to the `--notes` path (create or overwrite):

```json
{
  "commit_message": "fix: address review comments (<short scope>)",
  "threads": [
    {"id": "<thread id>", "kind": "fix|question|skip", "path": "<file>", "line": 12,
     "summary": "<one line: what the reviewer asked>",
     "reply": "<see below>"}
  ]
}
```

`reply` is Markdown, short and plain (no emojis, no thanks/apologies):
- **fix**: one bullet per change, `- <what changed>` (e.g. ``- Added a null check on `user.id` ``).
  `pr-fix-finish` appends `Fixed in <sha>.` below it.
- **question**: the answer in one or two sentences; bullets if it has several points.
- **skip**: one line on why it needs my decision.

Write `reply` in `language` from my settings, whatever language the reviewer used. Keep technical
terms, code identifiers, file paths and error messages in English as they are (e.g. "null check",
"race condition", `formatDateTime`). No footer; `pr-fix-finish` adds it.

## 5. Report

List each thread as `kind · path:line · summary`, then the files you changed, then the self-check
result (ran / skipped, and what it changed). With `--headless`, the last line of your output must be
one line starting with `STATUS: `, e.g.
`STATUS: 3 fixed, 1 question, 1 skipped` or `STATUS: failed, <short reason>`.
