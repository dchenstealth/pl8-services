#!/usr/bin/env bash
# End-to-end check of PL8's async lifecycle against a deployed environment,
# driven through pl8-interface:
#   1. A blocks B; A -> DONE; B must reach TODO.
#   2. C blocks D; C deleted; the IssueBlocker must be swept and D reach TODO.
#   3. Both DLQs must be empty.
# Creates its own Space and deletes it (and its Issues) at the end.
#
# Usage: scripts/smoke-test.sh <environment>   (requires aws, jq)
set -euo pipefail

env="${1:?usage: $0 <environment>}"
function_name="${env}-pl8-interface"
space="smoke-$(date +%s)"
timeout_seconds=120
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

invoke() {
  local operation="$1" params="$2"
  aws lambda invoke --function-name "$function_name" \
    --cli-binary-format raw-in-base64-out \
    --payload "$(jq -nc --arg op "$operation" --argjson p "$params" \
      '{operation: $op, params: $p}')" \
    "$tmp/out.json" >/dev/null
  if [[ "$(jq -r .ok "$tmp/out.json")" != "true" ]]; then
    echo "FAIL: $operation $params -> $(cat "$tmp/out.json")" >&2
    exit 1
  fi
  jq -c .data "$tmp/out.json"
}

create_issue() {
  invoke create_issue "$(jq -nc --arg s "$space" --arg t "$1" \
    '{space_id: $s, title: $t, description: "pl8-services smoke test", status: "TODO"}')" \
    | jq -r .issue_id
}

issue_field() {
  invoke get_issue "$(jq -nc --arg s "$space" --arg i "$1" \
    '{space_id: $s, issue_id: $i}')" | jq -r ".$2"
}

block() {
  invoke add_issue_blocker "$(jq -nc --arg s "$space" --arg a "$1" --arg b "$2" \
    '{blocking_issue_space_id: $s, blocking_issue_id: $a,
      blocked_issue_space_id: $s, blocked_issue_id: $b}')" >/dev/null
}

wait_for() {
  local description="$1"; shift
  local deadline=$((SECONDS + timeout_seconds))
  until "$@"; do
    if ((SECONDS > deadline)); then
      echo "FAIL: timed out waiting for $description" >&2
      exit 1
    fi
    sleep 2
  done
  echo "ok: $description"
}

status_is() { [[ "$(issue_field "$1" status)" == "$2" ]]; }

blockers_empty() {
  [[ "$(invoke get_issue_blockers "$(jq -nc --arg s "$space" --arg i "$1" \
    '{space_id: $s, blocked_issue_id: $i}')" | jq '.items | length')" == 0 ]]
}

invoke create_space "$(jq -nc --arg s "$space" \
  '{space_id: $s, name: $s, description: "pl8-services smoke test"}')" >/dev/null
echo "Space: $space"

# 1. Blocker satisfied by DONE
a="$(create_issue A)"; b="$(create_issue B)"
block "$a" "$b"
if ! status_is "$b" BLOCKED; then
  echo "FAIL: B not BLOCKED after add_issue_blocker" >&2
  exit 1
fi
echo "ok: B BLOCKED after add_issue_blocker"
invoke transition_issue "$(jq -nc --arg s "$space" --arg i "$a" \
  '{space_id: $s, issue_id: $i, status: "DONE"}')" >/dev/null
wait_for "B TODO after A DONE" status_is "$b" TODO

# 2. Blocker swept by delete
c="$(create_issue C)"; d="$(create_issue D)"
block "$c" "$d"
invoke delete_issue "$(jq -nc --arg s "$space" --arg i "$c" \
  '{space_id: $s, issue_id: $i}')" >/dev/null
wait_for "D's blocker swept after C deleted" blockers_empty "$d"
wait_for "D TODO after C deleted" status_is "$d" TODO

# 3. Nothing dead-lettered
for queue in "${env}-pl8-stream-handler-dlq" "${env}-pl8-event-handler-dlq"; do
  url="$(aws sqs get-queue-url --queue-name "$queue" --query QueueUrl --output text)"
  depth="$(aws sqs get-queue-attributes --queue-url "$url" \
    --attribute-names ApproximateNumberOfMessages \
    --query Attributes.ApproximateNumberOfMessages --output text)"
  if [[ "$depth" != 0 ]]; then
    echo "FAIL: $queue has $depth messages" >&2
    exit 1
  fi
  echo "ok: $queue empty"
done

# Cleanup
for issue in "$a" "$b" "$d"; do
  invoke delete_issue "$(jq -nc --arg s "$space" --arg i "$issue" \
    '{space_id: $s, issue_id: $i}')" >/dev/null
done
invoke delete_space "$(jq -nc --arg s "$space" '{space_id: $s}')" >/dev/null
echo "PASS"
