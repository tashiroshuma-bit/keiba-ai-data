#!/usr/bin/env bash
# Persist the derived research candidate to a dedicated Git branch, then re-fetch and verify.
# Run ONLY in trusted main-branch scheduled/manual/push GitHub Actions, never on PRs.
set -euo pipefail
SRC="data/friday/available_historical_subset.sqlite"
CHECKSUM_FILE="$SRC.sha256"
BRANCH="data/friday-sql-candidate"
[[ -f "$SRC" && -f "$CHECKSUM_FILE" ]] || { echo "NOT_READY: candidate not created" >&2; exit 2; }
expected="$(cut -d ' ' -f 1 "$CHECKSUM_FILE")"
actual="$(sha256sum "$SRC" | cut -d ' ' -f 1)"
[[ "$actual" == "$expected" ]] || { echo "NOT_READY: candidate sha mismatch" >&2; exit 2; }
[[ "$(sqlite3 -readonly "$SRC" 'PRAGMA quick_check;')" == ok ]] || exit 2
[[ "$(sqlite3 -readonly "$SRC" 'SELECT COUNT(*) FROM tracked_result_runner;')" -gt 0 ]] || exit 2
[[ "$(sqlite3 -readonly "$SRC" 'SELECT COUNT(*) FROM tracked_profile_past_run;')" -gt 0 ]] || exit 2
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
cp "$SRC" "$work/candidate.sqlite"
code_sha="$(git rev-parse HEAD)"
if git ls-remote --exit-code --heads origin "$BRANCH" > /dev/null; then
  git fetch origin "$BRANCH"
  git checkout -B "$BRANCH" FETCH_HEAD
else
  git checkout -b "$BRANCH"
fi
mkdir -p snapshots
cp "$work/candidate.sqlite" snapshots/friday_sql_candidate.sqlite
sha256sum snapshots/friday_sql_candidate.sqlite > snapshots/friday_sql_candidate.sqlite.sha256
printf 'scope=PARTIAL_RETROSPECTIVE_NOT_CANONICAL\nsource_code_sha=%s\nsaved_utc=%s\ncandidate_sha256=%s\n' \
  "$code_sha" "$(date -u +%FT%TZ)" "$expected" > snapshots/friday_sql_candidate.status
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git add snapshots/friday_sql_candidate.sqlite snapshots/friday_sql_candidate.sqlite.sha256 snapshots/friday_sql_candidate.status
if ! git diff --cached --quiet; then
  git commit -m "Store replayable JRA retrospective candidate DB (not official canonical)"
  git push origin "HEAD:refs/heads/$BRANCH"
else
  echo "No candidate change"
fi
# A second fetch from the remote is a real persistence/read-back check.
git fetch origin "$BRANCH"
git show FETCH_HEAD:snapshots/friday_sql_candidate.sqlite > "$work/readback.sqlite"
readback_sha="$(sha256sum "$work/readback.sqlite" | cut -d ' ' -f 1)"
[[ "$readback_sha" == "$expected" ]] || { echo "FAIL: remote read-back SHA mismatch"; exit 2; }
[[ "$(sqlite3 -readonly "$work/readback.sqlite" 'PRAGMA quick_check;')" == ok ]] || exit 2
printf 'REMOTE_PERSISTED_AND_VERIFIED branch=%s sha256=%s runners=%s flat_profile_runs=%s\n' \
 "$BRANCH" "$expected" \
 "$(sqlite3 -readonly "$work/readback.sqlite" 'SELECT COUNT(*) FROM tracked_result_runner;')" \
 "$(sqlite3 -readonly "$work/readback.sqlite" 'SELECT COUNT(*) FROM tracked_profile_past_run;')"
