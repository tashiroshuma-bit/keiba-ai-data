#!/usr/bin/env bash
# Independent-run persisted SQLite data-branch readback against freshly parsed JRA results.
set -euo pipefail
localdb="data/friday/archived_official_history.sqlite"
if [[ $# -ge 1 ]]; then localdb="$1"; fi
[[ -f "$localdb" ]] || { echo 'NOT_READY: fresh SQLite missing'; exit 2; }
branch="data/friday-three-year-history"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
git fetch --no-tags origin "refs/heads/$branch"
git show FETCH_HEAD:snapshots/archived_official_history.sqlite > "$tmp/remote.sqlite"
git show FETCH_HEAD:snapshots/archived_official_history.sqlite.sha256 > "$tmp/remote.sha256"
git show FETCH_HEAD:snapshots/archived_official_history.status > "$tmp/remote.status"
expected="$(cut -d ' ' -f 1 "$tmp/remote.sha256")"
claimed="$(sed -n 's/^sha256=//p' "$tmp/remote.status")"
actual="$(sha256sum "$tmp/remote.sqlite" | cut -d ' ' -f 1)"
[[ "$expected" == "$claimed" && "$actual" == "$expected" ]] || { echo 'FAIL: source snapshot checksum disagreement'; exit 2; }
[[ "$(sqlite3 -readonly "$tmp/remote.sqlite" 'PRAGMA quick_check;')" == ok ]] || exit 2
[[ -z "$(sqlite3 -readonly "$tmp/remote.sqlite" 'PRAGMA foreign_key_check;')" ]] || exit 2
[[ "$(sqlite3 -readonly "$tmp/remote.sqlite" 'SELECT COUNT(*) FROM archive_races;')" == 12688 ]] || exit 2
[[ "$(sqlite3 -readonly "$tmp/remote.sqlite" 'SELECT COUNT(*) FROM archive_runners;')" == 174749 ]] || exit 2
[[ "$(sqlite3 -readonly "$tmp/remote.sqlite" "SELECT COUNT(*) FROM archive_races WHERE metadata_verified=1 AND year BETWEEN 2023 AND 2025;")" == 9599 ]] || exit 2
[[ "$(sqlite3 -readonly "$tmp/remote.sqlite" "SELECT COUNT(*) FROM v_archive_observed_starts WHERE jockey_id LIKE 'jra-jockey:pw04kmk%';")" == 163789 ]] || exit 2
if [[ "$(sha256sum "$localdb" | cut -d ' ' -f 1)" != "$actual" ]]; then
  # Different SQLite page layout across SQLite versions is possible; authoritative check is logical content.
  diff -u <(sqlite3 -readonly "$tmp/remote.sqlite" .dump) <(sqlite3 -readonly "$localdb" .dump)
fi
printf 'INDEPENDENT_FULL_HISTORY_SNAPSHOT_READBACK_SUCCESS sha=%s races=12688 all_horse_results=174749 verified_flat_2023_2025=9599\n' "$actual"
