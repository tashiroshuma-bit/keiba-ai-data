#!/usr/bin/env bash
set -euo pipefail
DB="${1:-data/friday/history.sqlite}"
OUT="${2:-reports/friday_source_audit}"
mkdir -p "$OUT"
[[ -f "$DB" ]] || { echo 'NOT_READY: DB absent'; exit 2; }
[[ "$(sqlite3 -readonly "$DB" 'PRAGMA quick_check;')" == 'ok' ]] || exit 2
[[ -z "$(sqlite3 -readonly "$DB" 'PRAGMA foreign_key_check;')" ]] || exit 2
for pair in 'historical_starts' 'declared_entries' 'source_manifest'; do
 count="$(sqlite3 -readonly "$DB" "SELECT COUNT(*) FROM $pair;")"
 printf '%s=%s\n' "$pair" "$count"
 [[ "$count" -gt 0 ]] || { echo "NOT_READY: empty $pair" > "$OUT/status.txt"; exit 2; }
done
# Every target entry must have a verified official card manifest.
bad_cards="$(sqlite3 -readonly "$DB" "SELECT COUNT(*) FROM declared_entries e LEFT JOIN source_manifest m ON m.source_sha256=e.source_sha256 WHERE m.source_kind IS NOT 'official_card' OR m.verification_status IS NOT 'verified';")"
[[ "$bad_cards" == 0 ]] || { echo "NOT_READY: unverified cards $bad_cards" > "$OUT/status.txt"; exit 2; }
sqlite3 -readonly -header -csv "$DB" < sql/friday_report.sql > "$OUT/report.csv"
sqlite3 -readonly -header -csv "$DB" < sql/friday_conditions.sql > "$OUT/conditions.csv"
sqlite3 -readonly -header -csv "$DB" < sql/friday_recent5.sql > "$OUT/recent5.csv"
sha256sum "$DB" > "$OUT/db.sha256"
printf 'REPORT_GENERATED_FROM_LOADED_DB; official completeness and target roster audit still required\n' > "$OUT/status.txt"
