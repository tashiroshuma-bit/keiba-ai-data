#!/usr/bin/env bash
# Restore normalized JRA source-backed SQLite from an earlier successful Actions run.
# Persist to the dedicated data branch with explicit partial/coverage status and remote read-back.
set -euo pipefail
src="data/friday/archived_official_history.sqlite"
[[ -s "$src" ]] || { echo 'NOT_READY: normalized source-backed SQLite absent'; exit 2; }
source_sha="$(sha256sum "$src" | cut -d ' ' -f 1)"
claim="$(cut -d ' ' -f 1 "$src.sha256")"
[[ "$source_sha" == "$claim" ]] || { echo 'FAIL: source DB checksum file mismatch'; exit 2; }
[[ "$(sqlite3 -readonly "$src" 'PRAGMA quick_check;')" == ok ]] || exit 2
[[ -z "$(sqlite3 -readonly "$src" 'PRAGMA foreign_key_check;')" ]] || exit 2
races="$(sqlite3 -readonly "$src" 'SELECT COUNT(*) FROM archive_races;')"
runners="$(sqlite3 -readonly "$src" 'SELECT COUNT(*) FROM archive_runners;')"
[[ "$races" -ge 10000 && "$runners" -ge 100000 ]] || { echo 'NOT_READY: insufficient archive source'; exit 2; }
branch="data/friday-three-year-history"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
cp "$src" "$tmp/source.sqlite"
cp "$src.sha256" "$tmp/source.sha256"
code_sha="$(git rev-parse HEAD)"
if git ls-remote --exit-code --heads origin "$branch" >/dev/null; then
  git fetch --no-tags origin "$branch"
  git checkout -B "$branch" FETCH_HEAD
else
  git checkout -b "$branch"
fi
mkdir -p snapshots
cp "$tmp/source.sqlite" snapshots/archived_official_history.sqlite
sha256sum snapshots/archived_official_history.sqlite > snapshots/archived_official_history.sqlite.sha256
printf 'scope=PARTIAL_2023_2026_OFFICIAL_ORIGINAL_SHA_VERIFIED_NOT_FULL_FLAT_COVERAGE\ncode_sha=%s\nsource_archive_workflow_run=43774658187\nraces=%s\nhorse_results=%s\nsha256=%s\nsaved_utc=%s\n' "$code_sha" "$races" "$runners" "$source_sha" "$(date -u +%FT%TZ)" > snapshots/archived_official_history.status
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git add snapshots/archived_official_history.sqlite snapshots/archived_official_history.sqlite.sha256 snapshots/archived_official_history.status
if ! git diff --cached --quiet; then
  git commit -m "Store source-backed JRA 2023-2026 archive SQLite (partial coverage; not full-production)"
  git push origin "HEAD:refs/heads/$branch"
else
  echo 'Persisted archive is unchanged'
fi
git fetch --no-tags origin "$branch"
git show FETCH_HEAD:snapshots/archived_official_history.sqlite > "$tmp/readback.sqlite"
readback="$(sha256sum "$tmp/readback.sqlite" | cut -d ' ' -f 1)"
[[ "$readback" == "$source_sha" ]] || { echo 'FAIL: persisted remote read-back SHA mismatch'; exit 2; }
[[ "$(sqlite3 -readonly "$tmp/readback.sqlite" 'PRAGMA quick_check;')" == ok ]] || exit 2
[[ -z "$(sqlite3 -readonly "$tmp/readback.sqlite" 'PRAGMA foreign_key_check;')" ]] || exit 2
[[ "$(sqlite3 -readonly "$tmp/readback.sqlite" 'SELECT COUNT(*) FROM archive_runners;')" == "$runners" ]] || exit 2
echo "ARCHIVE_PERSISTED_REMOTE_READBACK_VERIFIED branch=$branch races=$races runners=$runners sha256=$source_sha"
