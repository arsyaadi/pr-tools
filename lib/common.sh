# Shared by the pr-tools scripts (sourced by bash): install root, settings, GitHub account, and the
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
PR_AGENTS=()                 # agents offered in the menu bar (claude codex agy); default: every one installed
PR_TOOLS_CONFIG=${PR_TOOLS_CONFIG:-$HOME/.config/pr-tools/config}
[[ -f $PR_TOOLS_CONFIG ]] && source "$PR_TOOLS_CONFIG"
# where install.sh found the agent CLIs (nvm's node for codex, ~/.local/bin, …): SwiftBar has a bare PATH
[[ -f $PR_TOOLS_ROOT/.agent-path ]] && PATH="$PATH:$(<"$PR_TOOLS_ROOT/.agent-path")"

# Run as PR_GH_ACCOUNT (set per account by the menu bar). Everything started after this, including
# the agent's gh calls and the guard scripts, inherits GH_TOKEN.
use_gh_account() {
  [[ -n ${PR_GH_ACCOUNT:-} ]] || return 0
  GH_TOKEN=$(gh auth token --user "$PR_GH_ACCOUNT" 2>/dev/null) ||
    { echo "gh account $PR_GH_ACCOUNT is not logged in" >&2; exit 1; }
  export GH_TOKEN
}

# Agents. PR_AGENT (set per menu action) picks the CLI; default: the first of PR_AGENTS.
(( ${#PR_AGENTS[@]} )) || for a in claude codex agy; do command -v "$a" >/dev/null && PR_AGENTS+=("$a"); done
PR_AGENT=${PR_AGENT:-${PR_AGENTS[0]:-claude}}
agent_name() { case ${1:-$PR_AGENT} in claude) echo Claude ;; codex) echo Codex ;; agy) echo Antigravity ;; *) echo "$1" ;; esac; }
skill() { [[ $PR_AGENT == codex ]] && echo "\$$1" || echo "/$1"; }   # how the agent invokes a skill
require_agent() {
  command -v "$PR_AGENT" >/dev/null && return 0
  notify "pr-tools" "$(agent_name) CLI ($PR_AGENT) not found"; exit 1
}

# agent_run review|fix <prompt> <out-prefix> [session]: PR_AGENT headless, limited to what that mode
# needs. Claude: --allowedTools. Codex: sandbox without network, plus the allow rules install.sh
# writes to ~/.codex/rules/pr-tools.rules. Antigravity: the allow list install.sh adds to its
# settings.json (headless denies everything else). Anything outside those can't write to GitHub.
# Writes <prefix>.jsonl (raw) and <prefix>.log (final answer, cost, denied calls); sets
# AGENT_SESSION, which a later agent_run (or agent_cli) can resume.
agent_run() {
  local mode=$1 prompt=$2 out=$3 session=${4:-} cache=$HOME/.cache/pr-fix
  AGENT_SESSION=$session
  case $PR_AGENT in
  claude)
    local allow=("Bash(pr-tools-config)" "Bash(git log:*)" "Bash(git show:*)" "Bash(git diff:*)" "Bash(git blame:*)")
    # disableAllHooks: user hooks (e.g. command rewriters) would break the allow rules
    local args=(--settings '{"disableAllHooks":true}' --output-format stream-json --verbose)
    if [[ $mode == review ]]; then
      allow+=("Bash(pr-review-post:*)" "Bash(gh pr view:*)" "Bash(gh pr diff:*)" "Bash(gh repo view:*)"
        "Bash(gh api user --jq .login)" "Bash(git fetch:*)" "Bash(git merge-base:*)"
        "Skill(pr-review)" "Skill(ponytail-review)" "Skill(ponytail:ponytail-review)")
      args+=(--no-session-persistence)
    else
      allow+=("Bash(pr-threads:*)" "Bash(git status:*)" "Skill(pr-fix)")
      args+=(--permission-mode acceptEdits --add-dir "$cache")
      [[ -z $session ]] && AGENT_SESSION=$(uuidgen | tr '[:upper:]' '[:lower:]')
      if [[ -n $session ]]; then args+=(--resume "$session"); else args+=(--session-id "$AGENT_SESSION"); fi
    fi
    claude -p "$prompt" "${args[@]}" --allowedTools "${allow[@]}" </dev/null >"$out.jsonl" 2>&1
    jq -rs 'map(select(.type == "result"))[-1] | (.result // "no result (see .jsonl)"),
      "COST: $\((.total_cost_usd // 0) * 100 | round / 100)",
      (.permission_denials // [] | .[] | "DENIED: \(.tool_name) \(.tool_input.command // (.tool_input | tostring))")' \
      "$out.jsonl" >"$out.log" 2>/dev/null || cp "$out.jsonl" "$out.log" ;;
  codex)
    local args=(--json -o "$out.last" --skip-git-repo-check -c 'approval_policy="never"')
    # sandbox via -c: `codex exec resume` takes no -s / --add-dir
    local eph=(); [[ $mode == review ]] && eph=(--ephemeral)   # reviews are never resumed
    if [[ $mode == review ]]; then args+=(-c 'sandbox_mode="read-only"')
    else args+=(-c 'sandbox_mode="workspace-write"' -c "sandbox_workspace_write.writable_roots=[\"$cache\"]"); fi
    rm -f "$out.last"
    if [[ -n $session ]]; then codex exec resume "${args[@]}" "$session" "$prompt"
    else codex exec "${eph[@]}" "${args[@]}" "$prompt"; fi </dev/null >"$out.jsonl" 2>"$out.err"
    [[ -n $session ]] || AGENT_SESSION=$(jq -r 'select(.type == "thread.started") | .thread_id' "$out.jsonl" 2>/dev/null | head -1)
    { cat "$out.last" 2>/dev/null || { echo "no result (see .jsonl)"; tail -5 "$out.err"; }
      jq -r 'select(.type == "item.completed" and .item.type == "command_execution" and .item.exit_code != 0)
        | "FAILED: \(.item.command)"' "$out.jsonl" 2>/dev/null; } >"$out.log" ;;
  agy)
    local args=(--output-format json --print-timeout 30m)
    [[ $mode == fix ]] && args+=(--mode accept-edits --add-dir "$cache")
    [[ -n $session ]] && args+=(--conversation "$session")
    agy -p "$prompt" "${args[@]}" </dev/null >"$out.jsonl" 2>"$out.err"
    [[ -n $session ]] || AGENT_SESSION=$(jq -r '.conversation_id // empty' "$out.jsonl" 2>/dev/null)
    { jq -r '(.response | select(. != "") // "no result"), (.denied_actions // [] | .[] | "DENIED: \(.display_name)")' \
        "$out.jsonl" 2>/dev/null || echo "no result (see .jsonl)"
      cat "$out.err"; } >"$out.log" ;;
  esac
}

# agent_cli <prompt> [session]: shell command that opens PR_AGENT interactively (resuming session)
agent_cli() {
  local q=${1:+$(printf %q "$1")}
  case $PR_AGENT in
    claude) echo "claude ${2:+--resume $2 }$q" ;;
    codex) echo "codex ${2:+resume $2 }$q" ;;
    agy) echo "agy ${2:+--conversation $2 }${q:+-i $q}" ;;
  esac
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
