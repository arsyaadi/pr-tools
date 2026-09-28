# Shared by the pr-tools scripts (sourced by bash): plugin root, settings, GitHub account, and the
# macOS bits (notifications, editor, terminal, menu bar refresh).

PR_TOOLS_ROOT=${PR_TOOLS_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)}
export PR_TOOLS_ROOT
export PATH="$PR_TOOLS_ROOT/bin:$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

# Settings: defaults here, overridden by ~/.config/pr-tools/config (see config.example).
PR_LANGUAGE=English          # language for review comments and thread replies
PR_SKIP_TITLE=               # regex; PRs whose title matches are not reviewed (e.g. ^Release)
PR_EDITOR=                   # CLI that opens a folder for reviewing fixes (zed, code, cursor); default: first found
PR_TERMINAL=                 # ghostty or terminal, for interactive sessions; default: ghostty if installed
PROJECT_DIRS=()              # folders searched first for local clones; default: scan $HOME
GH_ACCOUNTS=()               # accounts in the menu bar; default: every `gh auth status` account
PR_TOOLS_CONFIG=${PR_TOOLS_CONFIG:-$HOME/.config/pr-tools/config}
[[ -f $PR_TOOLS_CONFIG ]] && source "$PR_TOOLS_CONFIG"

# Run as PR_GH_ACCOUNT (set per account by the menu bar). Everything started after this, including
# Claude's gh calls and the guard scripts, inherits GH_TOKEN.
use_gh_account() {
  [[ -n ${PR_GH_ACCOUNT:-} ]] || return 0
  GH_TOKEN=$(gh auth token --user "$PR_GH_ACCOUNT" 2>/dev/null) ||
    { echo "gh account $PR_GH_ACCOUNT is not logged in" >&2; exit 1; }
  export GH_TOKEN
}

# Shell prefix that re-selects the account in a new terminal (apps opened via `open` don't inherit env).
gh_env_prefix() {
  [[ -n ${PR_GH_ACCOUNT:-} ]] && printf 'export GH_TOKEN=$(gh auth token --user %s); ' "$PR_GH_ACCOUNT"
}

# notify <title> <message> [url opened on click]; clickable with terminal-notifier, plain otherwise
notify() {
  terminal-notifier -title "$1" -group "pr-tools-$1" -message "$2" ${3:+-open "$3"} >/dev/null 2>&1 && return 0
  command -v osascript >/dev/null &&
    osascript -e 'on run a' -e 'display notification (item 2 of a) with title (item 1 of a)' -e 'end run' "$1" "$2" >/dev/null 2>&1
  return 0
}

refresh_menubar() {
  [[ $(uname) == Darwin ]] && open -g "swiftbar://refreshplugin?name=pr-tools" 2>/dev/null
  return 0
}

# open_editor <dir>: PR_EDITOR, else the first of zed / code / cursor, else Finder
open_editor() {
  local e=$PR_EDITOR
  if [[ -z $e ]]; then
    for e in zed code cursor; do command -v "$e" >/dev/null && break; e=; done
  fi
  if [[ -n $e ]] && command -v "$e" >/dev/null; then "$e" "$1"; else open "$1"; fi
}

# open_terminal <dir> <command>: new terminal window in <dir> running <command> in a login shell
open_terminal() {
  local dir=$1 cmd=$2 t=$PR_TERMINAL
  [[ -z $t ]] && { [[ -d /Applications/Ghostty.app ]] && t=ghostty || t=terminal; }
  if [[ $t == ghostty ]]; then
    open -na Ghostty.app --args --working-directory="$dir" -e "${SHELL:-/bin/zsh}" -lic "$cmd"
  else
    osascript -e 'on run a' -e 'tell application "Terminal"' -e 'activate' -e 'do script (item 1 of a)' \
      -e 'end tell' -e 'end run' "cd $(printf %q "$dir") && $cmd" >/dev/null
  fi
}

# repo name and number from a PR url
pr_parts() {   # sets: owner repo num slug
  [[ $1 =~ ^https://github\.com/([^/]+)/([^/]+)/pull/([0-9]+)/?$ ]] || { echo "bad PR url: $1" >&2; exit 2; }
  owner=${BASH_REMATCH[1]} repo=${BASH_REMATCH[2]} num=${BASH_REMATCH[3]} slug=$owner/$repo
}
