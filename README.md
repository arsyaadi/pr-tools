# pr-tools

A Claude Code plugin for GitHub pull requests:

- **`/pr-tools:pr-review`** reviews a PR for bugs and drafts the findings as inline comments in a
  pending review. Nobody else sees it until you submit it.
- **`/pr-tools:pr-fix`** takes the unresolved review comments on your own PR, makes the changes in a
  separate worktree and leaves them uncommitted so you can go through the diff first.
- **A macOS menu bar** (SwiftBar, optional) that lists PRs waiting for your review, new commits on PRs
  you already reviewed, and your own PRs, with buttons that run the above in the background.

Claude never submits a review and never pushes on its own. See [Safety](#safety).

## Install

```bash
claude plugin marketplace add arsyaadi/pr-tools
claude plugin install pr-tools@pr-tools
```

You need Claude Code, [`gh`](https://cli.github.com) (logged in with `gh auth login`), `jq` and `git`.

For the menu bar (macOS):

```bash
brew install --cask swiftbar
brew install terminal-notifier   # optional: clickable notifications
```

then run `/pr-tools:setup-menubar` in Claude Code.

## Reviewing a PR

```
/pr-tools:pr-review https://github.com/owner/repo/pull/123
/pr-tools:pr-review            # the PR of the branch you're on
```

- Two agents look for bugs in parallel: one reads the diff (Opus), one reads the git history of the
  touched code (Sonnet). A third scores every finding.
- 80 and up becomes an inline comment. 50–79 becomes an inline comment marked as lower confidence.
  Below 50 is dropped. With nothing left, it drafts an LGTM.
- If you reviewed the PR before, only the commits since your last review are checked.
- You see the list first and pick what to drop, then it creates the pending review. On your own PR it
  posts a comment instead, since GitHub doesn't let you approve your own PR.
- Add `--lean` for an extra over-engineering pass (needs the
  [ponytail](https://github.com/DietrichGebert/ponytail) plugin).

To submit, use the menu bar, or run this in a terminal (GitHub's own "Finish your review" box drops
the summary Claude wrote):

```bash
~/.claude/plugins/cache/pr-tools/pr-tools/*/bin/pr-review-submit <pr-url> APPROVE   # or COMMENT / REQUEST_CHANGES
```

Run the review from a local clone of the repo when you can: the history check needs it.

## Fixing review comments

```
/pr-tools:pr-fix https://github.com/owner/repo/pull/123 --notes /tmp/pr-123-notes.json
```

The menu bar is the easier way in: every PR of yours with unresolved comments gets a
"Fix N comments with Claude" button. Then:

1. Claude checks out the branch in its own worktree, sorts each thread into fix / question / skip,
   and edits the code for the fixes. Nothing is committed. Your editor opens on the worktree.
2. You read the diff. "Follow up with Claude…" sends feedback ("drop that helper", "undo the change
   in auth.ts") into the same Claude session, as many times as you like.
3. "Commit, push and reply" commits what's left, pushes and replies to each fixed thread with the
   commit, then resolves it. Or push yourself and use "Reply to fixed threads". Questions and skipped
   threads are left for you.

## Menu bar

One submenu per `gh` account:

- **Needs review**: PRs where your review is requested.
- **New commits since my review**: PRs you reviewed that got new commits.
- **My PRs**: CI state and unresolved comments, with the fix buttons.

The number in the menu bar is how many PRs are waiting on you. While Claude is reviewing or fixing, it
turns into a sync symbol with the number of running jobs. Holding Option on a button gives the
interactive version, which opens a terminal instead of running in the background.

## Settings

Everything has a default. To change something, copy the example and uncomment what you need:

```bash
mkdir -p ~/.config/pr-tools
cp ~/.claude/plugins/cache/pr-tools/pr-tools/*/config.example ~/.config/pr-tools/config
```

| Setting | Default | |
|---|---|---|
| `PR_LANGUAGE` | English | Language for review comments and replies |
| `PR_FIXED_IN` | `Fixed in` | Text before the commit in replies to fixed threads |
| `PR_SKIP_TITLE` | none | Regex of PR titles not to review, e.g. `^Release` |
| `PR_EDITOR` | zed, code or cursor | Where prepared fixes open |
| `PR_TERMINAL` | Ghostty if installed, else Terminal | For interactive sessions |
| `PROJECT_DIRS` | scan `$HOME` | Folders to look in first for local clones |
| `GH_ACCOUNTS` | every `gh` account | Accounts shown in the menu bar |

Local clones are found by their `origin` remote, so folder names don't matter. For a second GitHub
account, `gh auth login` again; the menu bar picks it up and runs its actions as that account.

## Safety

- Every write to GitHub goes through a small script that decides what's allowed, not through Claude:
  `pr-review-post` strips any submit event (reviews on other people's PRs stay pending) and only
  writes to the PR being reviewed; `pr-thread-reply` only replies on your own PRs.
- Submitting a review is `pr-review-submit`, which asks you to confirm and isn't in Claude's allow
  list.
- Background runs can only use read-only `gh`/`git` commands and those scripts. Fix runs can only edit
  files inside their worktree.
- Pushes are plain `git push`, never forced. A rejected push stops without replying.
- Discarding a worktree only drops Claude's changes; leftovers after replying are stashed, not deleted.

Logs are in `~/.cache/pr-review` and `~/.cache/pr-fix` and are removed after 30 days.

## Uninstall

```bash
claude plugin uninstall pr-tools@pr-tools
claude plugin marketplace remove pr-tools
rm "$(defaults read com.ameba.SwiftBar PluginDirectory)/pr-tools.5m.sh"
```
