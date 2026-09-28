---
description: Fix unresolved review comments on your own PR as uncommitted changes (nothing is committed, pushed or replied)
argument-hint: <pr-url> --notes <path> [--headless]
model: claude-sonnet-5
effort: medium
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/bin/pr-threads:*), Bash(${CLAUDE_PLUGIN_ROOT}/bin/pr-tools-config), Bash(git status:*), Bash(git diff:*), Bash(git log:*), Bash(git show:*), Bash(git blame:*)
---

Address the unresolved review comments on the pull request in `$ARGUMENTS`. You only edit files in
the current directory (a checkout of the PR branch). You never commit, push or reply on GitHub:
I review your changes in my editor, and `pr-fix-finish` commits/pushes and replies afterwards.

## 1. Load

- Parse the PR URL, the `--notes <path>` file path, and whether `--headless` was passed
  (`--headless`: nobody is watching, never ask).
- `${CLAUDE_PLUGIN_ROOT}/bin/pr-tools-config` → my settings; `language` is for the replies you draft.
- `${CLAUDE_PLUGIN_ROOT}/bin/pr-threads <url>` → PR info and the unresolved threads (id, path, line,
  isOutdated, comments). Stop if the PR isn't mine (`mine: false`) or has no unresolved threads.
- `git log -1 --format=%H` must equal `headRefOid`; if not, stop and say the checkout is stale.

## 2. Triage each thread

Read the whole thread (later comments can change the ask) and the code around `path:line`.

- **fix**: a concrete, local change the reviewer asked for (rename, null check, missing case, move
  code, typo, small refactor). Make the smallest change that satisfies it, in the repo's style. Don't
  touch unrelated code and don't reformat files.
- **question**: the reviewer asks why/what, or wants discussion. Don't change code; draft an answer
  from the code and history.
- **skip**: I should decide: disagreement, product/behavior decisions, large redesigns, unclear asks,
  or outdated threads whose code no longer exists. Say why.

Don't build or run tests (only read-only git is allowed). If a fix needs a follow-up you can't verify,
say so in its reply.

## 3. Write the notes file

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

## 4. Report

List each thread as `kind · path:line · summary`, then the files you changed. With `--headless`,
the last line of your output must be one line starting with `STATUS: `, e.g.
`STATUS: 3 fixed, 1 question, 1 skipped` or `STATUS: failed, <short reason>`.
