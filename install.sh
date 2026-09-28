#!/usr/bin/env bash
# Install or update pr-tools for Claude Code, Codex and Antigravity. Safe to re-run.
#   curl -fsSL https://raw.githubusercontent.com/arsyaadi/pr-tools/main/install.sh | bash
# Run from a clone (./install.sh) to install that clone instead.
set -euo pipefail

repo=https://github.com/arsyaadi/pr-tools.git
bindir=$HOME/.local/bin
here=$(cd "$(dirname "${BASH_SOURCE[0]:-.}")" && pwd -P)
say() { printf '%s\n' "$*"; }

for c in git gh jq; do
  command -v "$c" >/dev/null || { say "Missing $c: install it first (macOS: brew install $c)."; exit 1; }
done

# 1. Source: this clone, or ~/.local/share/pr-tools (cloned, or updated with a fast-forward pull)
if [[ -f $here/skills/pr-review/SKILL.md ]]; then
  root=$here
else
  root=${PR_TOOLS_HOME:-$HOME/.local/share/pr-tools}
  if [[ -d $root/.git ]]; then git -C "$root" pull --ff-only --quiet; else git clone --quiet --depth 1 "$repo" "$root"; fi
fi
say "pr-tools: $root ($(git -C "$root" log -1 --format=%h 2>/dev/null || echo local))"

# link <target> <link>: symlink, but never replace a real file or folder someone else put there
link() {
  if [[ -e $2 && ! -L $2 ]]; then say "  skipped $2: exists and isn't a symlink"; return; fi
  ln -sfn "$1" "$2"
}

# 2. Scripts on PATH (the skills call them by name)
mkdir -p "$bindir"
for f in "$root"/bin/*; do link "$f" "$bindir/${f##*/}"; done

# 3. Skills into every agent found
skills_to() {
  mkdir -p "$1"
  for s in "$root"/skills/*/; do s=${s%/}; link "$s" "$1/${s##*/}"; done
  say "  $2: $1"
}
found=0
say "Skills:"
if command -v claude >/dev/null || [[ -d $HOME/.claude ]]; then
  skills_to "$HOME/.claude/skills" "Claude Code"
  mkdir -p "$HOME/.claude/agents" && link "$root/agents/pr-bug-hunter.md" "$HOME/.claude/agents/pr-bug-hunter.md"
  found=1
fi
if command -v codex >/dev/null || [[ -d ${CODEX_HOME:-$HOME/.codex} ]]; then
  skills_to "${CODEX_HOME:-$HOME/.codex}/skills" "Codex"; found=1
fi
if command -v agy >/dev/null || [[ -d $HOME/.gemini/config ]]; then
  skills_to "$HOME/.gemini/config/skills" "Antigravity"; found=1
fi
(( found )) || say "  no supported agent found (Claude Code, Codex, Antigravity); install one and re-run"

# 4. Headless permissions for the menu bar's background runs (what each agent may run unprompted)
paths=$(for c in claude codex agy node; do command -v "$c" >/dev/null && dirname "$(command -v "$c")"; done | awk '!s[$0]++' | paste -sd: -)
printf '%s\n' "$paths" >"$root/.agent-path"   # SwiftBar's PATH is bare; nvm's node is needed by codex
if command -v codex >/dev/null; then
  # allowed commands run outside the sandbox; everything else runs sandboxed with no network,
  # so it can't write to GitHub
  mkdir -p "${CODEX_HOME:-$HOME/.codex}/rules"
  cat >"${CODEX_HOME:-$HOME/.codex}/rules/pr-tools.rules" <<'RULES'
# pr-tools (install.sh): commands /pr-review and /pr-fix may run outside the sandbox.
prefix_rule(pattern = ["gh", "pr", ["view", "diff"]])
prefix_rule(pattern = ["gh", "repo", "view"])
prefix_rule(pattern = ["gh", "api", "user", "--jq", ".login"])
prefix_rule(pattern = ["git", "fetch"])
prefix_rule(pattern = [["pr-review-post", "pr-threads", "pr-tools-config"]])
RULES
  say "Codex rules: ${CODEX_HOME:-$HOME/.codex}/rules/pr-tools.rules"
fi
agy_settings=$HOME/.gemini/antigravity-cli/settings.json
if command -v agy >/dev/null; then
  # headless agy denies every command not in permissions.allow
  mkdir -p "${agy_settings%/*}"; [[ -s $agy_settings ]] || echo '{}' >"$agy_settings"
  jq '.permissions.allow = ((.permissions.allow // []) as $a | $a + ($add - $a))' --argjson add '[
    "command(gh pr view)", "command(gh pr diff)", "command(gh repo view)", "command(gh api user --jq .login)",
    "command(git fetch)", "command(git blame)", "command(git log)", "command(git show)", "command(git diff)",
    "command(git merge-base)", "command(git status)",
    "command(pr-review-post)", "command(pr-threads)", "command(pr-tools-config)"]' \
    "$agy_settings" >"$agy_settings.tmp" && mv "$agy_settings.tmp" "$agy_settings"
  say "Antigravity allow list: $agy_settings"
fi

# 5. Settings (kept on updates)
cfg=$HOME/.config/pr-tools/config
[[ -f $cfg ]] || { mkdir -p "${cfg%/*}"; cp "$root/config.example" "$cfg"; say "Settings: created $cfg"; }

# 6. Menu bar, when SwiftBar is installed (macOS)
if [[ -d /Applications/SwiftBar.app ]]; then
  say "Menu bar:"; "$root/bin/pr-tools-setup-menubar" | sed 's/^/  /'
fi

# 7. What's left for the user
say ""
case ":$PATH:" in *":$bindir:"*) ;; *) say "Add $bindir to your PATH (e.g. in ~/.zshrc: export PATH=\"\$HOME/.local/bin:\$PATH\")." ;; esac
gh auth status >/dev/null 2>&1 || say "Log in to GitHub: gh auth login"
say "Done. Restart your agent, then: /pr-review <pr-url> (Claude Code, Antigravity) or \$pr-review <pr-url> (Codex)."
