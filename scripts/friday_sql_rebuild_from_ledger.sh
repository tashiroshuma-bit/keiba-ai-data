#!/usr/bin/env bash
# Rebuild SQLite from versioned CSV ledger. Python-free and fail-closed.
set -euo pipefail
LEDGER="data/friday/ledger"
TARGET="data/friday/history.sqlite"
ORIGINALS="data/friday/originals"
if [[ $# -ge 1 ]]; then LEDGER="$1"; fi
if [[ $# -ge 2 ]]; then TARGET="$2"; fi
if [[ $# -ge 3 ]]; then ORIGINALS="$3"; fi
for executable in sqlite3 sha256sum mktemp; do
  command -v "$executable" >/dev/null || { echo "NOT_READY: missing $executable" >&2; exit 2; }
done
for name in source_manifest races historical_starts declared_entries; do
  if [[ ! -s "$LEDGER/$name.csv" ]]; then
    echo "NOT_READY: missing or empty $LEDGER/$name.csv" >&2
    exit 2
  fi
done
mkdir -p "$(dirname "$TARGET")"
work="$(mktemp -d "$(dirname "$TARGET")/.friday-rebuild.XXXXXX")"
trap 'rm -rf "$work"' EXIT
DB="$work/history.sqlite"
sqlite3 -bail "$DB" < sql/friday_schema.sql
cat > "$work/import.sql" <<EOF
.bail on
PRAGMA foreign_keys=ON;
.mode csv
.import --skip 1 "$LEDGER/source_manifest.csv" source_manifest
.import --skip 1 "$LEDGER/races.csv" races
.import --skip 1 "$LEDGER/historical_starts.csv" historical_starts
.import --skip 1 "$LEDGER/declared_entries.csv" declared_entries
EOF
sqlite3 -bail "$DB" < "$work/import.sql"
for table in source_manifest races historical_starts declared_entries; do
  count="$(sqlite3 -readonly "$DB" "SELECT COUNT(*) FROM $table;")"
  if [[ "$count" == 0 ]]; then
    echo "NOT_READY: $table has zero records" >&2
    exit 2
  fi
done
if [[ "$(sqlite3 -readonly "$DB" 'PRAGMA quick_check;')" != ok ]]; then
  echo "NOT_READY: quick_check failed" >&2
  exit 2
fi
if [[ -n "$(sqlite3 -readonly "$DB" 'PRAGMA foreign_key_check;')" ]]; then
  echo "NOT_READY: foreign_key_check failed" >&2
  exit 2
fi
# Verification flag alone is not proof: original bytes are required.
while IFS='|' read -r sha url kind status; do
  if [[ ! "$sha" =~ ^[a-f0-9]{64}$ || "$status" != verified ]]; then
    echo "NOT_READY: invalid manifest entry" >&2
    exit 2
  fi
  case "$url" in
    https://www.jra.go.jp/*|https://jra.jp/*) ;;
    *) echo "NOT_READY: non-JRA source URL" >&2; exit 2 ;;
  esac
  if [[ "$kind" != official_card && "$kind" != official_result ]]; then
    echo "NOT_READY: unexpected kind" >&2
    exit 2
  fi
  if [[ ! -f "$ORIGINALS/$sha" ]]; then
    echo "NOT_READY: original source missing for $sha" >&2
    exit 2
  fi
  actual="$(sha256sum "$ORIGINALS/$sha" | cut -d ' ' -f 1)"
  if [[ "$actual" != "$sha" ]]; then
    echo "NOT_READY: original SHA mismatch for $sha" >&2
    exit 2
  fi
done < <(sqlite3 -readonly -separator '|' "$DB" "SELECT source_sha256,source_url,source_kind,verification_status FROM source_manifest ORDER BY source_sha256;")
# Source kinds must match referenced record types.
kind_errors="$(sqlite3 -readonly "$DB" "SELECT (SELECT COUNT(*) FROM races r JOIN source_manifest m ON r.source_sha256=m.source_sha256 WHERE m.source_kind!='official_result') + (SELECT COUNT(*) FROM declared_entries e JOIN source_manifest m ON e.source_sha256=m.source_sha256 WHERE m.source_kind!='official_card');")"
if [[ "$kind_errors" != 0 ]]; then
  echo "NOT_READY: source kind mismatches $kind_errors" >&2
  exit 2
fi
# Runtime DB is derived. Source ledger is the persistent canonical input.
mv -f "$DB" "$TARGET"
sha256sum "$TARGET" > "$TARGET.sha256"
printf 'REBUILT_FROM_LEDGER: %s\n' "$TARGET"
sqlite3 -readonly "$TARGET" "SELECT 'races='||COUNT(*) FROM races; SELECT 'historical_starts='||COUNT(*) FROM historical_starts; SELECT 'declared_entries='||COUNT(*) FROM declared_entries;"
