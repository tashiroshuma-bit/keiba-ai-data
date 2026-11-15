#!/usr/bin/env bash
# Independent job/run readback of the permanent SQL-only JRA partial DB.
# Python-free. Does not change snapshots and does not assert full Friday readiness.
set -euo pipefail
remote_ref="refs/heads/data/friday-sql-candidate"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
git fetch --no-tags origin "$remote_ref"
git show FETCH_HEAD:snapshots/friday_sql_candidate.sqlite > "$tmp/remote.sqlite"
git show FETCH_HEAD:snapshots/friday_sql_candidate.sqlite.sha256 > "$tmp/remote.sha256"
git show FETCH_HEAD:snapshots/friday_sql_candidate.status > "$tmp/remote.status"
expected="$(awk 'NR==1{print $1}' "$tmp/remote.sha256")"
actual="$(sha256sum "$tmp/remote.sqlite" | cut -d ' ' -f 1)"
asserted="$(sed -n 's/^candidate_sha256=//p' "$tmp/remote.status")"
scope="$(sed -n 's/^scope=//p' "$tmp/remote.status")"
test "$actual" = "$expected" || { echo 'FAIL: downloaded bytes differ from snapshot SHA file'; exit 1; }
test "$actual" = "$asserted" || { echo 'FAIL: downloaded bytes differ from snapshot status'; exit 1; }
test "$scope" = "PARTIAL_RETROSPECTIVE_NOT_CANONICAL" || { echo 'FAIL: invalid snapshot scope'; exit 1; }
test "$(sqlite3 -readonly "$tmp/remote.sqlite" 'PRAGMA quick_check;')" = "ok"
test -z "$(sqlite3 -readonly "$tmp/remote.sqlite" 'PRAGMA foreign_key_check;')"
remote_results="$(sqlite3 -readonly "$tmp/remote.sqlite" 'SELECT COUNT(*) FROM tracked_result_runner;')"
remote_profiles="$(sqlite3 -readonly "$tmp/remote.sqlite" 'SELECT COUNT(*) FROM tracked_profile_past_run;')"
remote_sources="$(sqlite3 -readonly "$tmp/remote.sqlite" 'SELECT COUNT(*) FROM tracked_source_db;')"
test "$remote_results" = "486" || { echo "FAIL: expected 486 observed subset rows, got $remote_results"; exit 1; }
test "$remote_profiles" = "610" || { echo "FAIL: expected 610 verified-profile flat-history rows, got $remote_profiles"; exit 1; }
test "$remote_sources" = "3" || { echo "FAIL: expected 3 provenance dbs, got $remote_sources"; exit 1; }
# Verify the stored data can be reconstructed independently in THIS fresh runner
# from the committed source databases, without downloading temporary CI artifacts.
bash scripts/friday_seed_tracked_jra.sh "$tmp/rebuilt.sqlite" > "$tmp/rebuild.log"
diff -u \
  <(sqlite3 -readonly "$tmp/remote.sqlite" '.dump') \
  <(sqlite3 -readonly "$tmp/rebuilt.sqlite" '.dump')
printf 'REMOTE_CROSS_RUN_READBACK_OK sha256=%s results=%s profile_flat_runs=%s source_dbs=%s\n' \
  "$actual" "$remote_results" "$remote_profiles" "$remote_sources"
echo 'SCOPE=PARTIAL_RETROSPECTIVE_NOT_CANONICAL; full Friday cards and jockey IDs still NOT_READY'
