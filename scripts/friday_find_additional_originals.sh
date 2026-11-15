#!/usr/bin/env bash
# Find still-live historical JRA official source artifacts not included in known 46 shards.
set -euo pipefail
if [[ -z "$GH_TOKEN" ]]; then echo 'Missing GitHub Actions token'; exit 2; fi
out="reports/friday_full_backfill/missing16_artifacts.tsv"
mkdir -p "$(dirname "$out")"
: > "$out"
for page in $(seq 1 50); do
  response="$(gh api "repos/$GITHUB_REPOSITORY/actions/artifacts?per_page=100&page=$page")"
  echo "$response" | jq -r '.artifacts[] | select(.name|startswith("jra-review-missing16-shard-")) | [.id,.name,.expired,.size_in_bytes,.created_at,.workflow_run.id] | @tsv' >> "$out"
  count="$(echo "$response" | jq '.artifacts|length')"
  oldest="$(echo "$response" | jq -r '[.artifacts[].created_at] | min // ""')"
  if [[ "$count" -lt 100 || "$oldest" < "2026-11-10" ]]; then break; fi
done
echo 'EXTRA_OFFICIAL_ARTIFACTS:'
cat "$out"
found="$(wc -l < "$out")"
echo "missing16_artifacts_found=$found"
test "$found" -eq 8 || { echo 'NOT_READY: expected 8 additional archived sources not found'; exit 2; }
test "$(awk -F'\t' '$3=="false" {n++} END{print n+0}' "$out")" -eq 8 || exit 2
