#!/usr/bin/env bash
# End-to-end check of PL8's async lifecycle against a deployed environment,
# driven through pl8-interface:
#   1. A blocks B; A -> DONE; B must reach TODO.
#   2. C blocks D; C deleted; the IssueBlocker must be swept and D reach TODO.
#   3. E gets a comment and is deleted; the IssueComment must be swept.
#   4. F gets an attachment: the bytes are POSTed to the presigned target,
#      confirmed and downloaded back; F is then deleted and both the
#      IssueAttachment row and its S3 object must be swept.
#   5. Both DLQs must be empty.
# Creates its own Space and deletes it (and its Issues) on exit, pass or fail.
#
# Usage: scripts/smoke-test.sh <environment>   (requires aws, jq, curl)
set -euo pipefail

env="${1:?usage: $0 <environment>}"
function_name="${env}-pl8-interface"
space="smoke-$(date +%s)"
creator="pl8-services-smoke-test"
timeout_seconds=120
tmp="$(mktemp -d)"
space_created=false
issues=()
bucket=""
attachment_key=""

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
  invoke create_issue "$(jq -nc --arg s "$space" --arg t "$1" --arg c "$creator" \
    '{space_id: $s, title: $t, description: "pl8-services smoke test",
      status: "TODO", creator: $c}')" \
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

# Uploads a file to a presigned POST target. Every field S3 signed for has to
# be sent, and the file part must come last, or S3 rejects the request.
post_to_s3() {
  local target="$1" file="$2"
  local -a form=()
  local field value
  while IFS=$'\t' read -r field value; do
    form+=(--form "$field=$value")
  done < <(jq -r '.fields | to_entries[] | [.key, .value] | @tsv' <<<"$target")
  curl --fail --silent --show-error -X POST "${form[@]}" \
    --form "file=@$file" "$(jq -r .url <<<"$target")" >/dev/null
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

# Best effort: deletes that fail (e.g. an Issue the test already deleted)
# are skipped so the rest still run. Each runs in a subshell because invoke
# exits on failure.
cleanup() {
  local status=$?
  set +e
  local issue
  # ${a[@]+...}: bash < 4.4 (e.g. macOS's /bin/bash) treats an empty array
  # as unbound under set -u.
  for issue in ${issues[@]+"${issues[@]}"}; do
    (invoke delete_issue "$(jq -nc --arg s "$space" --arg i "$issue" \
      '{space_id: $s, issue_id: $i}')") >/dev/null 2>&1
  done
  # An object whose row was swept is already gone; this covers a run that
  # failed between the upload and the sweep.
  if [[ -n "$attachment_key" ]]; then
    aws s3api delete-object --bucket "$bucket" --key "$attachment_key" \
      >/dev/null 2>&1
  fi
  if [[ "$space_created" == true ]]; then
    (invoke delete_space "$(jq -nc --arg s "$space" '{space_id: $s}')") >/dev/null 2>&1 \
      || echo "warning: could not delete Space $space" >&2
  fi
  rm -rf "$tmp"
  exit "$status"
}
trap cleanup EXIT

# The bucket is named account-regionally (see infra/s3.tf), so it is matched by
# prefix rather than composed here.
bucket="$(aws s3api list-buckets \
  --query "Buckets[?starts_with(Name, '${env}-pl8-bucket')].Name | [0]" \
  --output text)"
if [[ -z "$bucket" || "$bucket" == "None" ]]; then
  echo "FAIL: no ${env}-pl8-bucket in this account and region" >&2
  exit 1
fi

status_is() { [[ "$(issue_field "$1" status)" == "$2" ]]; }

blockers_empty() {
  [[ "$(invoke get_issue_blockers "$(jq -nc --arg s "$space" --arg i "$1" \
    '{space_id: $s, blocked_issue_id: $i}')" | jq '.items | length')" == 0 ]]
}

comments_empty() {
  [[ "$(invoke get_issue_comments "$(jq -nc --arg s "$space" --arg i "$1" \
    '{space_id: $s, issue_id: $i}')" | jq '.items | length')" == 0 ]]
}

attachments_empty() {
  [[ "$(invoke get_issue_attachments "$(jq -nc --arg s "$space" --arg i "$1" \
    '{space_id: $s, issue_id: $i}')" | jq '.items | length')" == 0 ]]
}

object_gone() {
  ! aws s3api head-object --bucket "$bucket" --key "$1" >/dev/null 2>&1
}

invoke create_space "$(jq -nc --arg s "$space" --arg c "$creator" \
  '{space_id: $s, name: $s, description: "pl8-services smoke test",
    creator: $c}')" >/dev/null
space_created=true
echo "Space: $space"

# 1. Blocker satisfied by DONE
a="$(create_issue A)"; issues+=("$a")
b="$(create_issue B)"; issues+=("$b")
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
c="$(create_issue C)"; issues+=("$c")
d="$(create_issue D)"; issues+=("$d")
block "$c" "$d"
invoke delete_issue "$(jq -nc --arg s "$space" --arg i "$c" \
  '{space_id: $s, issue_id: $i}')" >/dev/null
wait_for "D's blocker swept after C deleted" blockers_empty "$d"
wait_for "D TODO after C deleted" status_is "$d" TODO

# 3. Comments swept by delete. An Issue is deleted whatever its num_comments,
# unlike a Space, so nothing here has to remove the comment first.
e="$(create_issue E)"; issues+=("$e")
invoke create_issue_comment "$(jq -nc --arg s "$space" --arg i "$e" --arg c "$creator" \
  '{space_id: $s, issue_id: $i, body: "pl8-services smoke test", creator: $c}')" >/dev/null
if comments_empty "$e"; then
  echo "FAIL: E's comment missing before E was deleted" >&2
  exit 1
fi
echo "ok: E has a comment"
invoke delete_issue "$(jq -nc --arg s "$space" --arg i "$e" \
  '{space_id: $s, issue_id: $i}')" >/dev/null
wait_for "E's comment swept after E deleted" comments_empty "$e"

# 4. Attachment round trip, then swept by delete. initiate answers with the
# attachment plus an `upload` target (`url` and the form `fields` to POST
# with); get_issue_attachment answers with the attachment plus a
# `download_url`, which is null until the attachment is UPLOADED (see
# pl8-interface's operations.yaml). The object key is read from the signed
# fields rather than from the attachment or recomposed, because that field is
# what S3 will actually write to.
f="$(create_issue F)"; issues+=("$f")
printf 'pl8-services smoke test attachment\n' > "$tmp/attachment.txt"
size="$(wc -c < "$tmp/attachment.txt" | tr -d ' ')"
initiated="$(invoke initiate_issue_attachment_upload \
  "$(jq -nc --arg s "$space" --arg i "$f" --arg c "$creator" --argjson z "$size" \
    '{space_id: $s, issue_id: $i, name: "attachment.txt",
      content_type: "text/plain", size: $z, creator: $c}')")"
attachment_id="$(jq -r .attachment.attachment_id <<<"$initiated")"
attachment_key="$(jq -r .upload.fields.key <<<"$initiated")"
post_to_s3 "$(jq -c .upload <<<"$initiated")" "$tmp/attachment.txt"
echo "ok: attachment bytes accepted by S3"

invoke confirm_issue_attachment_uploaded "$(jq -nc --arg s "$space" --arg i "$f" \
  --arg a "$attachment_id" \
  '{space_id: $s, issue_id: $i, attachment_id: $a}')" >/dev/null
downloadable="$(invoke get_issue_attachment "$(jq -nc --arg s "$space" --arg i "$f" \
  --arg a "$attachment_id" \
  '{space_id: $s, issue_id: $i, attachment_id: $a}')")"
download_url="$(jq -r '.download_url // empty' <<<"$downloadable")"
if [[ -z "$download_url" ]]; then
  echo "FAIL: no download URL for a confirmed attachment -> $downloadable" >&2
  exit 1
fi
curl --fail --silent --show-error --output "$tmp/downloaded.txt" "$download_url"
if ! cmp -s "$tmp/attachment.txt" "$tmp/downloaded.txt"; then
  echo "FAIL: downloaded attachment differs from what was uploaded" >&2
  exit 1
fi
echo "ok: attachment confirmed and downloaded unchanged"

invoke delete_issue "$(jq -nc --arg s "$space" --arg i "$f" \
  '{space_id: $s, issue_id: $i}')" >/dev/null
wait_for "F's attachment row swept after F deleted" attachments_empty "$f"
wait_for "F's S3 object reaped after F deleted" object_gone "$attachment_key"
attachment_key=""

# 5. Nothing dead-lettered
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

echo "PASS"
