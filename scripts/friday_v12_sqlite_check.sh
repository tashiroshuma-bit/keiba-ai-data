#!/usr/bin/env bash
set -euo pipefail
DB="${CANONICAL_DB:-private-data/jra_2023_2025_v12_horse_ids_full_20261111.sqlite}"
OUT="reports/friday_source_audit"
mkdir -p "$OUT"
EXPECTED="5d16777588420ac88bab5df21defb85d9346c2b918bb71859af06893752bcadd"
if ! command -v sqlite3 >/dev/null 2>&1; then
  printf 'NOT_READY: sqlite3 CLI missing\n' | tee "$OUT/status.txt"
  exit 2
fi
if [[ ! -f "$DB" ]]; then
  printf 'NOT_READY: canonical SQLite not mounted at %s\n' "$DB" | tee "$OUT/status.txt"
  exit 2
fi
actual="$(sha256sum "$DB" | cut -d ' ' -f 1)"
bytes="$(stat -c '%s' "$DB")"
if [[ "$actual" != "$EXPECTED" || "$bytes" != "362139648" ]]; then
  printf 'NOT_READY: checksum/size mismatch, sha256=%s bytes=%s\n' "$actual" "$bytes" | tee "$OUT/status.txt"
  exit 2
fi
if [[ "$(sqlite3 -readonly "$DB" 'PRAGMA quick_check;')" != "ok" ]]; then
  printf 'NOT_READY: SQLite quick_check failed\n' | tee "$OUT/status.txt"
  exit 2
fi
sqlite3 -readonly -header -csv "$DB" "SELECT name,type FROM sqlite_master WHERE type IN ('table','view') ORDER BY name;" > "$OUT/tables.csv"
sqlite3 -readonly "$DB" ".schema" > "$OUT/schema.sql"
printf 'SOURCE_VERIFIED: checksum, size, quick_check; schema exported; joins not yet certified\n' | tee "$OUT/status.txt"
