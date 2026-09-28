#!/bin/bash
# pr-tools menu bar body, run by the SwiftBar shim that /pr-tools:setup-menubar installs (the shim
# sets PR_TOOLS_ROOT to the installed plugin). One submenu per gh account: PRs needing my review,
# new commits on PRs I reviewed, my PRs. Every action runs as that account (PR_GH_ACCOUNT → GH_TOKEN).
source "$(dirname "$0")/../lib/common.sh"
bin=$PR_TOOLS_ROOT/bin

# accounts: GH_ACCOUNTS from the config if set, else every logged-in gh account (active first)
if (( ${#GH_ACCOUNTS[@]} )); then
  ACCOUNTS=("${GH_ACCOUNTS[@]}")
else
  ACCOUNTS=($(gh auth status --json hosts --jq '.hosts["github.com"] | sort_by(.active | not) | .[].login' 2>/dev/null))
fi

# menu actions that need the lib: interactive review in a terminal, opening prepared fixes
case $1 in
  review)   # review <pr-url> <account>: terminal in the local clone running /pr-tools:pr-review
    pr_parts "$2"; PR_GH_ACCOUNT=$3
    dir=$(pr-review-repo-dir "$slug") || dir=$HOME
    open_terminal "$dir" "$(gh_env_prefix)claude '/pr-tools:pr-review $2'"
    exit ;;
  editor) open_editor "$2"; exit ;;
esac

QUERY='query{
  viewer{login}
  reviewed: search(query:"is:pr is:open reviewed-by:@me -author:@me archived:false sort:updated-desc", type:ISSUE, first:20){
    nodes{... on PullRequest{number title url headRefOid repository{nameWithOwner}
      pending: reviews(states:PENDING, first:1){totalCount}
      reviews(last:30){nodes{author{login} state commit{oid}}}
      commits(last:50){nodes{commit{oid}}}}}}
  review: search(query:"is:pr is:open review-requested:@me archived:false", type:ISSUE, first:20){
    nodes{... on PullRequest{number title url repository{nameWithOwner}
      pending: reviews(states:PENDING, first:1){totalCount}}}}
  mine: search(query:"is:pr is:open author:@me archived:false sort:updated-desc", type:ISSUE, first:20){
    nodes{... on PullRequest{number title url isDraft headRefOid repository{nameWithOwner}
      reviewThreads(first:100){nodes{isResolved}}
      commits(last:1){nodes{commit{statusCheckRollup{state}}}}}}}
}'

# fetch every account in parallel
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
for a in "${ACCOUNTS[@]}"; do
  ( token=$(gh auth token --user "$a" 2>/dev/null) || { echo '{"error":"not logged in"}' >"$tmp/$a"; exit; }
    GH_TOKEN=$token gh api graphql -f query="$QUERY" >"$tmp/$a" 2>/dev/null || echo '{"error":"gh failed"}' >"$tmp/$a" ) &
done
wait

# PRs I reviewed whose head moved since my last review (skip ones already re-requested)
changed_tsv() {   # $1 json → repo, num, title, url, delta, pending
  jq -r '.data as $d | [$d.review.nodes[].url] as $req | $d.reviewed.nodes[] | select(.url | IN($req[]) | not) |
    ([.reviews.nodes[] | select(.author.login == $d.viewer.login and .state != "PENDING")] | last | .commit.oid) as $mine |
    select($mine != null and $mine != .headRefOid) |
    ([.commits.nodes[].commit.oid] | index($mine)) as $i |
    [(.repository.nameWithOwner | split("/")[1]), .number, .title[0:45], .url,
     (if $i == null then "changed" else ((.commits.nodes | length) - $i - 1) as $n | "+\($n) commit\(if $n > 1 then "s" else "" end)" end),
     .pending.totalCount] | @tsv' <<<"$1"
}

# menu bar: everything waiting on my review, all accounts together
total=0
for a in "${ACCOUNTS[@]}"; do
  j=$(<"$tmp/$a"); jq -e .data >/dev/null 2>&1 <<<"$j" || continue
  total=$((total + $(jq '.data.review.nodes | length' <<<"$j") + $(changed_tsv "$j" | grep -c .)))
done
# while Claude is reviewing or fixing comments: sync symbol + how many jobs are running;
# otherwise: PR symbol + how many PRs wait for my review. Each running job holds a .running lock,
# and the runners refresh this plugin when they start and finish.
running=$(find "$HOME/.cache/pr-review" "$HOME/.cache/pr-fix" -maxdepth 1 -name '*.running' 2>/dev/null | grep -c .)
if (( running )); then
  echo "$running | sfimage=arrow.triangle.2.circlepath"
else
  echo "$total | sfimage=arrow.triangle.pull"
fi
echo "---"

gray="color=#8e8e93,#98989d size=11"
act="size=12"
red="color=#ff453a,#ff6961"

# review actions for one PR inside an account submenu: running / submit my pending review / start
review_actions() {   # $1 account, $2 repo, $3 num, $4 url, $5 pending, $6 label
  local as="bash=/usr/bin/env param1=PR_GH_ACCOUNT=$1"
  if [[ -e $HOME/.cache/pr-review/$2-$3.running ]]; then
    echo "--    Claude is reviewing… | $gray"
  elif (( $5 )); then
    echo "--    Pending review: check it on GitHub | href=$4/files $act"
    for e in APPROVE:Approve COMMENT:Comment "REQUEST_CHANGES:Request changes"; do
      echo "--    Submit as ${e#*:} | $as param2=$bin/pr-review-submit param3=$4 param4=${e%%:*} terminal=false $act"
    done
  else
    echo "--    $6 with Claude | $as param2=$bin/pr-review-headless param3=$4 terminal=false $act"
    echo "--    $6 with Claude (interactive) | alternate=true bash='$SWIFTBAR_PLUGIN_PATH' param1=review param2=$4 param3=$1 terminal=false $act"
  fi
}

for a in "${ACCOUNTS[@]}"; do
  j=$(<"$tmp/$a")
  if ! jq -e .data >/dev/null 2>&1 <<<"$j"; then
    echo "$a · $(jq -r '.error // "error"' <<<"$j") | $red"
    continue
  fi
  requested=$(jq '.data.review.nodes | length' <<<"$j")
  changed=$(changed_tsv "$j"); new_commits=$(grep -c . <<<"$changed")
  # SwiftBar disables items without an action or color, even with a submenu → every parent gets a link
  echo "$a · $((requested + new_commits)) | href=https://github.com/pulls/review-requested"

  echo "--Needs review · $requested | $gray"
  (( requested )) || echo "--Nothing to review | $gray"
  while IFS=$'\t' read -r r num title url pending; do
    [[ -z $r ]] && continue
    echo "--$r #$num · $title | href=$url"
    review_actions "$a" "$r" "$num" "$url" "$pending" Review
  done < <(jq -r '.data.review.nodes[] | [(.repository.nameWithOwner | split("/")[1]), .number, .title[0:50], .url, .pending.totalCount] | @tsv' <<<"$j")

  if (( new_commits )); then
    echo "-----"
    echo "--New commits since my review · $new_commits | $gray"
    while IFS=$'\t' read -r r num title url delta pending; do
      echo "--$r #$num · $title · $delta | href=$url"
      review_actions "$a" "$r" "$num" "$url" "$pending" "Review new commits"
    done <<<"$changed"
  fi

  # My PRs (one level deeper). Option on a PR = headless self-review (not for titles matching PR_SKIP_TITLE).
  # Unresolved review threads → "Fix … with Claude" (pr-fix-prepare), then the finish steps.
  echo "-----"
  echo "--My PRs · $(jq '.data.mine.nodes | length' <<<"$j") | href=https://github.com/pulls"
  as="bash=/usr/bin/env param1=PR_GH_ACCOUNT=$a"
  fix=$HOME/.cache/pr-fix
  while IFS=$'\t' read -r ci r num title url unresolved head; do
    [[ -z $r ]] && continue
    s=$( ((unresolved > 1)) && echo s)
    meta=${ci#none}; (( unresolved )) && meta+="${meta:+ · }$unresolved comment$s"
    [[ -e $HOME/.cache/pr-review/$r-$num.running ]] && meta+="${meta:+ · }reviewing…"
    color=; [[ $ci == "CI failing" ]] && color=" $red"
    echo "----$r #$num · $title${meta:+ · $meta} | href=$url$color"
    [[ -z $PR_SKIP_TITLE || ! ${title#Draft: } =~ $PR_SKIP_TITLE ]] &&
      echo "----Review with Claude: $r #$num | alternate=true $as param2=$bin/pr-review-headless param3=$url terminal=false"
    finish="$as param2=$bin/pr-fix-finish param3=$url terminal=false refresh=true $act"
    if [[ -e $fix/$r-$num.running ]]; then
      echo "----    Claude is fixing the comments… | $gray"
    elif [[ -f $fix/$r-$num.json ]]; then
      dir=$(jq -r .dir "$fix/$r-$num.json"); base=$(jq -r .base "$fix/$r-$num.json")
      echo "----    Fixes ready: open in editor | bash='$SWIFTBAR_PLUGIN_PATH' param1=editor param2=$dir terminal=false $act"
      follow="$as param2=$bin/pr-fix-followup param3=$url terminal=false $act"
      echo "----    Follow up with Claude… | $follow"
      echo "----    Follow up with Claude (interactive) | $follow param4=--interactive"
      echo "----    Commit, push and reply | $finish param4=commit"
      echo "----    Reply to fixed threads$([[ $head != "$base" ]] && echo " (pushed)") | $finish param4=reply"
      echo "----    Discard fixes | $finish param4=discard $red"
    elif (( unresolved )); then
      echo "----    Fix $unresolved comment$s with Claude | $as param2=$bin/pr-fix-prepare param3=$url terminal=false $act"
      echo "----    Fix $unresolved comment$s with Claude (interactive) | alternate=true $as param2=$bin/pr-fix-prepare param3=$url param4=--interactive terminal=false $act"
    fi
  done < <(jq -r '.data.mine.nodes[] |
    ({"SUCCESS":"CI passed","FAILURE":"CI failing","ERROR":"CI failing","PENDING":"CI running","EXPECTED":"CI running"}
       [.commits.nodes[0].commit.statusCheckRollup.state // ""] // "none") as $ci |   # tab-read drops empty fields
    [$ci, (.repository.nameWithOwner | split("/")[1]), .number,
     ((if .isDraft then "Draft: " else "" end) + .title[0:50]), .url,
     ([.reviewThreads.nodes[] | select(.isResolved | not)] | length), .headRefOid] | @tsv' <<<"$j")
done
echo "---"
echo "Open GitHub pulls | href=https://github.com/pulls"
