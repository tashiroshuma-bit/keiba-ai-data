#!/usr/bin/env bash
set -euo pipefail
command -v sqlite3 >/dev/null || { echo 'NOT_READY sqlite3 CLI missing'; exit 2; }
DB="${1:-data/friday/history.sqlite}"
mkdir -p "$(dirname "$DB")" reports/friday_source_audit
sqlite3 "$DB" < sql/friday_schema.sql
[[ "$(sqlite3 "$DB" 'PRAGMA quick_check;')" == ok ]]
[[ "$(sqlite3 "$DB" 'PRAGMA foreign_key_check;')" == "" ]]
# Production data is NOT fabricated: absent official imports means fail closed.
rows="$(sqlite3 -readonly "$DB" 'SELECT COUNT(*) FROM historical_starts;')"
entries="$(sqlite3 -readonly "$DB" 'SELECT COUNT(*) FROM declared_entries;')"
printf 'historical_starts=%s declared_entries=%s\n' "$rows" "$entries"
if [[ "$rows" == 0 || "$entries" == 0 ]]; then
  echo 'NOT_READY: no verified official historical starts or future cards loaded' | tee reports/friday_source_audit/status.txt
  exit 2
fi
sqlite3 -readonly -header -csv "$DB" < sql/friday_report.sql > reports/friday_source_audit/report.csv
echo 'SQL_COMPLETE_WITH_LOADED_DATA; official source coverage still requires reconciliation' | tee reports/friday_source_audit/status.txt
