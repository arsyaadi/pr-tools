# pr-tools

GitHub pull request skills for [Claude Code](https://claude.com/claude-code),
[Codex](https://openai.com/codex) and [Antigravity](https://antigravity.google):

- **`pr-review`** reviews a PR for bugs, security and performance problems, violations of the
  repo's own rules and code smells, and drafts the findings as inline comments in a pending review.
  Nobody else sees it until you submit it.
- **`pr-fix`** takes the unresolved review comments on your own PR, makes the changes in a separate
  worktree and leaves them uncommitted so you can go through the diff first.
- **A macOS menu bar** (SwiftBar, optional) that lists PRs waiting for your review, new commits on PRs
  you already reviewed, and your own PRs, with buttons that run the above in the background.

The agent never submits a review and never pushes on its own. See [Safety](#safety).

## Install

### Ask your agent

Paste this into Claude Code, Codex or Antigravity:

```text
Install pr-tools (https://github.com/arsyaadi/pr-tools) for me. Run:

curl -fsSL https://raw.githubusercontent.com/arsyaadi/pr-tools/main/install.sh | bash

Show me what it printed. If it lists something left to do (a missing tool, adding ~/.local/bin to
PATH, gh auth login), tell me the exact command for each, and run only the ones that don't need my
input or a password. Don't change anything else.
```

### Or run it yourself

```bash
curl -fsSL https://raw.githubusercontent.com/arsyaadi/pr-tools/main/install.sh | bash
```

You need `git`, `jq` and [`gh`](https://cli.github.com) (logged in with `gh auth login`). The script:

- keeps a copy in `~/.local/share/pr-tools` and links its scripts into `~/.local/bin`;
- links the skills into each agent it finds: `~/.claude/skills`, `~/.codex/skills`,
  `~/.gemini/config/skills`;
- creates `~/.config/pr-tools/config` on the first run;
- sets up the menu bar if [SwiftBar](https://swiftbar.app) is installed
  (`brew install --cask swiftbar`, plus `brew install terminal-notifier` for clickable notifications).

Run it again to update. Restart your agent afterwards. For just the skills, without the menu bar:

```bash
curl -fsSL https://raw.githubusercontent.com/arsyaadi/pr-tools/main/install.sh | bash -s -- --no-menubar
```

The skills need the scripts in `~/.local/bin` (that's where they post reviews and read threads), so
install with the script rather than copying only the `skills/` folder.

| Agent | Review | Fix |
|---|---|---|
| Claude Code, Antigravity | `/pr-review <pr-url>` | `/pr-fix <pr-url> --notes <file>` |
| Codex | `$pr-review <pr-url>` | `$pr-fix <pr-url> --notes <file>` |

## Reviewing a PR

```
/pr-review https://github.com/owner/repo/pull/123
/pr-review            # the PR of the branch you're on
/pr-review <pr-url> --full   # review the whole PR again, not just the commits since your last review
```

### What it checks

[`skills/pr-review/SKILL.md`](skills/pr-review/SKILL.md) runs up to five passes, each with its
own checklist. Which ones run depends on the files changed, not on how small the diff looks: a
docs-only PR gets only the quality pass. In Claude Code each pass is a subagent from
[`agents/`](agents) and they run in parallel; Codex and Antigravity run the same passes one after
another. Everything runs on the model your agent is set to.

| Pass | Looks for | Runs when | Checklist | Subagent |
|---|---|---|---|---|
| Bugs | Wrong logic, transactions, idempotency, state transitions, data integrity, contracts, dates, numbers, races, migrations | Code changed | [`correctness`](skills/pr-review/correctness-checklist.md) | `pr-bug-hunter` |
| History | A fix this PR undoes, a bug fixed here before, a file that usually changes alongside but didn't | Code changed, in a local clone | [`correctness`](skills/pr-review/correctness-checklist.md) | `pr-bug-hunter` |
| Quality | The repo's written rules and code smells | Always | [`quality`](skills/pr-review/quality-checklist.md) | `pr-quality-hunter` |
| Security, performance | Injection, XSS, broken access control, leaked secrets, SSRF; N+1 queries, unbounded work, missing indexes, pool exhaustion | Code or config changed | [`security-perf`](skills/pr-review/security-perf-checklist.md) | `pr-security-hunter` |
| Tests | Changed behavior with no test, assertions that can't fail, wrong mocks, flaky tests, old tests left asserting the old behavior | Code changed | [`testing`](skills/pr-review/testing-checklist.md) | `pr-test-hunter` |

- The **history** pass runs `git blame` on the lines the PR touches and reads the commits that
  wrote them. It only reports when that history shows the old behavior was deliberate (a fix
  commit, a test, a comment) and the PR drops it without saying why.
- The **quality** pass reads `CLAUDE.md`, `AGENTS.md`, `CONTRIBUTING.md`,
  `.github/copilot-instructions.md` and the docs they point to, from the base branch so the PR
  can't rewrite its own rules. On top of that it uses a general checklist drawn from Google's code
  review guide, Fowler's code smells and Sonar's complexity limits. That covers deep nesting,
  duplication, magic values, reinvented framework features and over-engineering, plus
  dependencies, API contracts, accessibility and translations when the diff touches them. On large
  PRs (over 10 files or 800 lines) it splits into groups of about 10 files.
- **Security and performance** findings have to show the path from untrusted input to the
  problem, or what grows with input and why nothing bounds it.

### How a review runs

1. **Load.** Reads the PR, its diff, every review thread and your settings. It stops on a closed or
   merged PR, a title matching `PR_SKIP_TITLE`, or a pending review you already have. On a draft it
   asks first.
2. **Scope.** If you reviewed the PR before, only the commits since your last review are checked
   (`--full` checks everything). Each of your unresolved comments is marked addressed, still open,
   changed or no longer relevant in the summary.
3. **Passes.** A short summary of the change goes to every pass, so changes the PR means to make
   aren't flagged. Renames and generated files are skipped. Issues already raised in a thread,
   resolved or not, by anyone, aren't raised again.
4. **Tests (optional).** In an interactive run where your working tree is at the PR's head commit,
   it can run the tests covering the change, after asking you, since that executes the PR's code.
   Background runs never do.
5. **Scoring.** A fresh subagent scores every finding (see below).
6. **Your pick.** You see the list and choose what to drop. If nothing is left, it drafts an LGTM.
7. **Post.** `pr-review-post` creates the pending review. On your own PR it posts a comment
   instead, since GitHub doesn't let you approve your own PR. If the PR got new commits during the
   review, nothing is posted: the line numbers may have moved, so run it again.

### How findings are scored

Every finding needs a concrete scenario and evidence: what triggers it, what breaks, and the code
that proves it. Text in the PR or repo can't instruct the reviewer. Each finding gets two separate
grades:

- **Confidence** (0–100) that it's real. 80 and up becomes an inline comment. 50–79 becomes an
  inline comment marked as lower confidence, saying what couldn't be verified. Below 50 is dropped,
  but a P0 or P1 issue gets one more look before that.
- **Severity**: P0 critical (exploitable hole, data loss, wrong money or permissions, outage), P1
  high (wrong on a common path, regression of an earlier fix), P2 medium (edge path, performance
  at realistic scale), P3 low (everything else).

A rule violation is scored like a bug: the rule has to really exist and cover the line, and a
measured value like cognitive complexity over 15 has to hold. Judgment calls become non-blocking
nits, at most 15 from the quality pass and 10 from the tests pass.

To submit, use the menu bar, or run this in a terminal (GitHub's own "Finish your review" box drops
the summary the agent wrote):

```bash
pr-review-submit <pr-url> APPROVE   # or COMMENT / REQUEST_CHANGES
```

Run the review from a local clone of the repo when you can: the history check needs it.

## Fixing review comments

```
/pr-fix https://github.com/owner/repo/pull/123 --notes /tmp/pr-123-notes.json
```

The menu bar is the easier way in: every PR of yours with unresolved comments gets a
"Fix N comments with …" button. Then:

1. The agent checks out the branch in its own worktree, sorts each thread into fix / question / skip,
   and edits the code for the fixes. It checks each suggestion against the code first: one that
   would be wrong becomes a question with the evidence instead of a change. Then a bug pass reads
   its own diff and corrects or drops a fix that broke something. Nothing is committed. Your editor
   opens on the worktree.
2. You read the diff. "Follow up with …" sends feedback ("drop that helper", "undo the change
   in auth.ts") into the same agent session, as many times as you like.
3. "Commit, push and reply" commits what's left, pushes and replies to each fixed thread with the
   commit, then resolves it. Or push yourself and use "Reply to fixed threads". Questions and skipped
   threads are left for you.

## Menu bar

One submenu per `gh` account. A pending review gets "Submit as Approve / Comment / Request changes"
and "Discard pending review"; both ask you to confirm first.

- **Needs review**: PRs where your review is requested.
- **New commits since my review**: PRs you reviewed that got new commits.
- **Pending reviews**: PRs where you have an unsubmitted review that isn't listed above (for
  example one started by running `pr-review` on a PR by URL).
- **My PRs**: CI state and unresolved comments, with the fix buttons.

With more than one agent installed, every review and fix button opens a "… with" submenu to pick
Claude, Codex or Antigravity (`PR_AGENTS` in the settings narrows or reorders the list). Follow-ups
go back to the agent that made the fixes.

The number in the menu bar is how many PRs are waiting on you. While an agent is reviewing or fixing, it
turns into a sync symbol with the number of running jobs. Holding Option on a button gives the
interactive version, which opens a terminal instead of running in the background.

## Settings

Everything has a default. To change something, uncomment it in `~/.config/pr-tools/config`
(created by the installer from `config.example`).

| Setting | Default | |
|---|---|---|
| `PR_LANGUAGE` | English | Language for review comments and replies |
| `PR_SKIP_TITLE` | none | Regex of PR titles not to review, e.g. `^Release` |
| `PR_EDITOR` | zed, code or cursor | Where prepared fixes open |
| `PR_TERMINAL` | Ghostty if installed, else Terminal | For interactive sessions |
| `PROJECT_DIRS` | scan `$HOME` | Folders to look in first for local clones |
| `GH_ACCOUNTS` | every `gh` account | Accounts shown in the menu bar |
| `PR_AGENTS` | every agent installed | Agents offered in the menu bar, first one is the default: `(claude codex agy)` |

Local clones are found by their `origin` remote, so folder names don't matter. For a second GitHub
account, `gh auth login` again; the menu bar picks it up and runs its actions as that account.

## Safety

- Every write to GitHub goes through a small script that decides what's allowed, not through the agent:
  `pr-review-post` strips any submit event (reviews on other people's PRs stay pending) and only
  writes to the PR being reviewed; `pr-thread-reply` only replies on your own PRs.
- Submitting a review is `pr-review-submit`, and deleting a pending one is `pr-review-discard`.
  Both ask you to confirm and aren't in any allow list. Discarding only deletes the draft: GitHub
  refuses to delete a submitted review that way.
- Background runs (the menu bar) can only use read-only `gh`/`git` commands and those scripts, on
  every agent. Fix runs can only edit files inside their worktree.
  - Claude Code: an exact `--allowedTools` list.
  - Codex: a sandbox without network; only the commands in `~/.codex/rules/pr-tools.rules` run
    outside it.
  - Antigravity: headless mode denies every command not in `permissions.allow` of
    `~/.gemini/antigravity-cli/settings.json`; the installer adds the same list there.

  The Codex rules and the Antigravity allow list also apply to your interactive sessions: those
  read-only commands, `pr-review-post` (pending reviews only) and `pr-threads` run without asking.
- Interactive runs use your agent's own approval prompts, so approve writes only when they go through
  those scripts.
- Pushes are plain `git push`, never forced. A rejected push stops without replying.
- Discarding a worktree only drops the agent's changes; leftovers after replying are stashed, not deleted.

Logs are in `~/.cache/pr-review` and `~/.cache/pr-fix` and are removed after 30 days.

## Evaluating changes

Before changing the skill, a checklist or an agent, check that reviews don't get worse.
[`eval/README.md`](eval/README.md) describes both ways:

- **Benchmark set.** Frozen PRs labeled by hand (known bugs, security holes, intended behavior
  changes, refactors, clean PRs), run headless at least twice each. Precision is the headline
  number; keep a change only if it doesn't drop.
- **Real runs.** The author's response to each finding on real PRs, plus per-run cost, angles and
  denied commands, logged in `eval/real-runs/` (gitignored, since the reviewed repos are private).
  `eval/report.py` turns them into an offline `eval/real-runs/report.html`:

```bash
python3 eval/report.py
```

Acceptance rate on real runs is only a proxy: authors accept wrong nits, and missed bugs don't
show up at all.

## Uninstall

```bash
rm -rf ~/.local/share/pr-tools ~/.config/pr-tools
find ~/.local/bin ~/.claude/skills ~/.claude/agents ~/.codex/skills ~/.gemini/config/skills \
  -maxdepth 1 -type l -lname '*pr-tools*' -delete
rm "$(defaults read com.ameba.SwiftBar PluginDirectory)/pr-tools.5m.sh" ~/.codex/rules/pr-tools.rules
```

The installer's entries in `permissions.allow` of `~/.gemini/antigravity-cli/settings.json` stay;
remove them by hand if you want.
