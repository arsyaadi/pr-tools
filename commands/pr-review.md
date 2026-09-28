---
description: Review a GitHub PR for bugs; findings become inline comments in a PENDING review (only you see it until you submit)
argument-hint: "[pr-url] [--lean] [--headless]"
model: claude-sonnet-5
effort: medium
allowed-tools: Bash(gh pr view:*), Bash(gh pr diff:*), Bash(gh repo view:*), Bash(gh api user:*), Bash(git fetch:*), Bash(git blame:*), Bash(git log:*), Bash(git show:*), Bash(git diff:*), Bash(git merge-base:*), Bash(${CLAUDE_PLUGIN_ROOT}/bin/pr-tools-config)
---

Review the pull request in `$ARGUMENTS` and draft the findings as a **pending** GitHub review.
Adapted from the official `code-review` plugin, with two differences: nothing is published (the
review stays PENDING until I submit it), and findings become inline comments.

Make a todo list first, then follow these steps precisely.

## 1. Load the PR

- Parse the PR URL (`https://github.com/<owner>/<repo>/pull/<n>`) and whether `--lean` / `--headless`
  were passed. No URL → use the current branch's PR (`gh pr view --json url --jq .url`); if the
  branch has no PR, stop and say so. `--headless` means nobody is watching: never ask, follow the headless rules below.
- `${CLAUDE_PLUGIN_ROOT}/bin/pr-tools-config` → my settings: `language` (for everything you write on
  GitHub) and `skip_title_regex` (empty = skip nothing).
- `gh api user --jq .login` → my login.
- `gh pr view <url> --json state,isDraft,title,body,author,baseRefName,headRefName,headRefOid,changedFiles,additions,deletions,reviews,url`
- `gh pr diff <url>` → the diff.

## 2. Eligibility (ask, don't guess)

- Closed or merged → stop.
- `skip_title_regex` is set and the title matches it → stop and say why.
- Draft → tell me it's a draft and ask whether to continue.
- I'm the PR's author → **self-review**: `pr-review-post` publishes it right away as a Comment
  (no pending step; GitHub allows nothing else on your own PR). Step 2b applies the same way.
- I already have a PENDING review → stop and tell me to submit or discard it on GitHub first
  (GitHub allows only one pending review per user per PR).
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
    commits). Tell me how many commits are new; don't ask. The Haiku summary still covers the whole
    PR for context, but agents review only the incremental diff.
  - Not an ancestor (rebased / force-pushed) → full review, and say why.
- Not in a clone → full review, and say why.

In incremental mode, the review `body` opens with `Incremental review: <k> new commits since
<LAST short sha>.` (in `language`). Inline comments must still sit on lines inside the PR's full diff (`gh pr diff`);
anything else goes in the body.

## 3. Review with parallel agents

Split the diff first: pure renames/moves (`rename from/to` with no hunks, or `similarity index 100%`)
carry no code to review. List them by name only and leave them out of what the agents read.

Use a Haiku agent to summarize the change (what and why, from title, body and the non-rename diff).
Pass that summary to every agent below and to the scorer, so intentional changes aren't flagged.
Then launch two `pr-tools:pr-bug-hunter` agents **in parallel**, one per angle. Each returns a list of issues:
file, line(s) on the new side, description, and the reason it was flagged.

- **Agent A: bugs in the diff** (`pr-tools:pr-bug-hunter` as defined: Opus 5.5). Read only the changed code and do a shallow scan for real bugs:
  wrong logic, broken edge cases, null/undefined handling, wrong API usage, data loss, security
  holes introduced by this change. Focus on large issues and skip nitpicks.
- **Agent B: history context** (`pr-tools:pr-bug-hunter` with the `model: sonnet` override). Only when the current directory is a clone of the PR's repo
  (`gh repo view --json nameWithOwner` matches `<owner>/<repo>`); otherwise skip it and say so.
  Run `git fetch origin <baseRefName> --quiet`, then use `git log` / `git blame origin/<baseRefName>`
  on the modified regions to find bugs that the history makes visible, e.g. reverting a previous
  fix or breaking an invariant other code relies on.

This review is about bugs: don't check the change against `CLAUDE.md`, `CONTRIBUTING.md` or style
guides.

## 4. Score and filter

Launch **one** Sonnet agent (`model: sonnet`) for all issues together. Give it the summary, the
non-rename diff inline (so it doesn't re-fetch anything) and the numbered issue list; it scores each
issue's confidence 0-100 that it is real (give it this rubric verbatim):

- 0: false positive that doesn't survive light scrutiny, or a pre-existing issue.
- 25: might be real, couldn't verify.
- 50: verified real, but a nitpick or rare in practice.
- 75: double-checked, very likely hit in practice, directly impacts functionality.
- 100: certain, confirmed by the evidence, will happen frequently.

Buckets: **≥ 80** → inline comments; **50-79** → "worth a look" inline comments (labelled as lower
confidence); **< 50** → drop. Also drop, whatever the score: pre-existing issues, issues on lines this PR didn't touch,
things a linter/typechecker/CI would catch, pedantic style, and intentional behavior changes that
are part of the PR's purpose. Don't build or run tests.

## 5. `--lean` only: over-engineering pass

If `--lean` was passed, run the `ponytail-review` skill on the diff (from the ponytail plugin; if
it isn't installed, skip this pass and say so). Keep its findings in a
separate group labelled `nit (non-blocking)`. They are not scored and never block the merge.

## 6. Show me before posting

Print a numbered list of everything that survived: `file:line`, one-line description, score and
bucket (inline / worth a look / nit). If nothing scored ≥ 50 and there are no nits:
- someone else's PR → skip the question and go to step 7 with no comments, only a `body` of
  `LGTM. No issues found (checked for bugs and regressions against history).` (in `language`).
  It stays pending, so I can submit it as Approve in one click.
- self-review → same, with `body` `LGTM (self-review). No issues found (checked for bugs and
  regressions against history).` It is published right away as a Comment.
Ask which ones to drop, then wait for my answer. With `--headless`, don't ask: keep everything
(I curate the pending review on GitHub).

## 7. Draft the pending review

Write each kept finding as a brief comment: no emojis, say what breaks and when, suggest the fix
in one or two lines. Nits start with `nit (non-blocking):`.

**Language:** write the review (comments and body) in `language` from my settings, whatever
language the PR uses. Keep technical terms, code identifiers, file paths and error messages in
English as they are (e.g. "race condition", "null check", `formatDateTime`); don't translate them.
The fixed phrases below are given in English: write them in `language` too. Footers stay as given.

- A finding whose line is on the new (RIGHT) side of a diff hunk → an inline comment
  `{"path", "line", "side": "RIGHT", "body"}`. For multi-line ranges add `start_line` and
  `start_side: "RIGHT"`.
- A finding outside the diff hunks → a bullet in the review `body`, linked as
  `https://github.com/<owner>/<repo>/blob/<headRefOid>/<path>#L<a>-L<b>` (full sha).
- `body` opens with one line: how many issues were found and that bugs were checked, e.g.
  `Found 2 issues (checked for bugs and regressions against history).`
- "Worth a look" findings (50-79) are inline comments too (same placement rules), starting with
  `**Worth a look (lower confidence):**`. Only ones outside the diff hunks go in the `body`,
  under a `**Worth a look (lower confidence)**` heading with a permalink each.
- `body` always ends with a blank line and then exactly this footer (also on LGTM reviews):
  `🤖 Reviewed with [Claude Code](https://claude.com/claude-code)`.
- Every inline comment ends with a blank line and then exactly:
  `<sub>🤖 Reviewed with [Claude Code](https://claude.com/claude-code)</sub>`.

Create the review with `${CLAUDE_PLUGIN_ROOT}/bin/pr-review-post`, the only allowed write path. It takes
`{"commit_id": "<headRefOid>", "body": "...", "comments": [...]}` on stdin, strips `event` so the
review stays PENDING, and refuses any PR other than the one being reviewed:

```
${CLAUDE_PLUGIN_ROOT}/bin/pr-review-post <pr-url> <<'JSON'
{...}
JSON
```

Don't call `gh api` to write anything yourself. If it fails with 422 because a line can't be
resolved, move those comments into `body` and retry once. Submitting is mine to do.

## 8. Hand over

Print the number of inline comments and body notes, plus `<pr-url>/files`. Remind me the review is
pending: I finish it on GitHub with "Finish your review" → Comment / Approve / Request changes.
GitHub's "Finish your review" box drops the drafted `body`, so tell me to submit with the pr-tools
menu bar ("Submit as …") or by running this myself in a terminal, which keeps it (never run it
yourself): `${CLAUDE_PLUGIN_ROOT}/bin/pr-review-submit <pr-url> APPROVE|COMMENT|REQUEST_CHANGES`.
For a self-review there is nothing to finish: it's already published as a Comment.

With `--headless`, the **last line** of your output must be one line starting with `STATUS: `
(it becomes the notification), e.g. `STATUS: pending review drafted, 2 inline + 1 worth a look`, `STATUS: self-review posted, 1 inline`,
`STATUS: no issues, LGTM drafted (pending)`, `STATUS: skipped, title matches the skip pattern`, `STATUS: stopped, you already have a
pending review`, `STATUS: failed, <short reason>`.
