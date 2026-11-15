#!/usr/bin/env bash
set -euo pipefail
echo 'SQL-ONLY GIT DATABASE INVENTORY — no migration performed'
while IFS= read -r db; do
  [[ -f "$db" ]] || continue
  printf '\nDB=%s BYTES=%s\n' "$db" "$(stat -c '%s' "$db")"
  sqlite3 -readonly "$db" "SELECT 'quick_check='||(SELECT quick_check FROM pragma_quick_check LIMIT 1);" || continue
  sqlite3 -readonly -separator '|' "$db" "SELECT 'TABLE='||name||' '||replace(substr(sql,1,330),char(10),' ') FROM sqlite_master WHERE type='table' ORDER BY name LIMIT 18;" || true
  for table in races runner_results horse_races horse_history horse_profiles jockey_stats jockey_history historical_starts race_results; do
    # Identifiers are hard-coded above; no untrusted SQL.
    if [[ "$(sqlite3 -readonly "$db" "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='$table';")" == 1 ]]; then
      sqlite3 -readonly "$db" "SELECT '$table='||COUNT(*) FROM $table;" || true
    fi
  done
done < <(git ls-files '*.sqlite')
