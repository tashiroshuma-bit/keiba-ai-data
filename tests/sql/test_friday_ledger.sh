#!/usr/bin/env bash
set -euo pipefail
root="$(mktemp -d)"
trap 'rm -rf "$root"' EXIT
mkdir -p "$root/ledger" "$root/originals" "$root/run_a" "$root/run_b"
printf 'synthetic-result-evidence\n' > "$root/result"
printf 'synthetic-card-evidence\n' > "$root/card"
result_sha="$(sha256sum "$root/result" | cut -d ' ' -f 1)"
card_sha="$(sha256sum "$root/card" | cut -d ' ' -f 1)"
cp "$root/result" "$root/originals/$result_sha"
cp "$root/card" "$root/originals/$card_sha"
cat > "$root/ledger/source_manifest.csv" <<EOF
source_sha256,source_url,captured_at_jst,source_kind,verification_status
$result_sha,https://www.jra.go.jp/datafile/seiseki/,2026-11-10T12:00:00+09:00,official_result,verified
$card_sha,https://www.jra.go.jp/,2026-11-13T12:00:00+09:00,official_card,verified
EOF
cat > "$root/ledger/races.csv" <<EOF
race_id,race_date,venue,race_number,surface,going,distance_m,source_sha256
past1,2026-11-01,Tokyo,1,turf,good,1600,$result_sha
past2,2026-11-08,Tokyo,2,dirt,heavy,1400,$result_sha
future,2026-11-22,Tokyo,3,turf,good,1600,$result_sha
EOF
# The schema requires Japanese official surface and going values.
sed -i -e 's/,turf,good,/,芝,良,/g' -e 's/,dirt,heavy,/,ダート,重,/g' "$root/ledger/races.csv"
cat > "$root/ledger/historical_starts.csv" <<'EOF'
race_id,horse_id,horse_name,horse_number,jockey_id,jockey_name,finish_position,started
past1,H1,TEST-H1,1,J1,TEST-J1,1,1
past1,H2,TEST-H2,2,J2,TEST-J2,2,1
past2,H1,TEST-H1,1,J2,TEST-J2,3,1
past2,H3,TEST-H3,2,J1,TEST-J1,1,1
future,H1,TEST-H1,1,J1,TEST-J1,1,1
EOF
cat > "$root/ledger/declared_entries.csv" <<EOF
target_race_id,target_date,venue,race_number,horse_number,horse_id,horse_name,jockey_id,jockey_name,source_sha256
target,2026-11-21,東京,1,1,H1,TEST-H1,J1,TEST-J1,$card_sha
target,2026-11-21,東京,1,2,H4,TEST-H4,J2,TEST-J2,$card_sha
EOF
# First run, report, second independent run: ledger must be sufficient to rebuild both.
bash scripts/friday_sql_rebuild_from_ledger.sh "$root/ledger" "$root/run_a/history.sqlite" "$root/originals"
bash scripts/friday_sql_report.sh "$root/run_a/history.sqlite" "$root/run_a/output"
bash scripts/friday_sql_rebuild_from_ledger.sh "$root/ledger" "$root/run_b/history.sqlite" "$root/originals"
sqlite3 -readonly "$root/run_a/history.sqlite" .dump > "$root/run_a/dump.sql"
sqlite3 -readonly "$root/run_b/history.sqlite" .dump > "$root/run_b/dump.sql"
cmp "$root/run_a/dump.sql" "$root/run_b/dump.sql"
# No future results leaked; 2 prior finishes.
grep -q 'TEST-H1,H1,TEST-J1,J1,2,1,2,50.0,100.0,2,2,2,100.0,100.0,1,1,1,100.0,100.0' "$root/run_a/output/report.csv"
test "$(($(wc -l < "$root/run_a/output/conditions.csv") - 1))" -gt 0
test "$(($(wc -l < "$root/run_a/output/recent5.csv") - 1))" -eq 2
# Removing an original must reject rebuild and must NOT overwrite last working DB.
before="$(sha256sum "$root/run_a/history.sqlite" | cut -d ' ' -f 1)"
rm "$root/originals/$result_sha"
set +e
bash scripts/friday_sql_rebuild_from_ledger.sh "$root/ledger" "$root/run_a/history.sqlite" "$root/originals"
code="$?"
set -e
test "$code" -eq 2 || { echo "FAIL: missing original not rejected, exit=$code"; exit 1; }
test "$(sha256sum "$root/run_a/history.sqlite" | cut -d ' ' -f 1)" = "$before"
echo 'PASS: ledger rebuilt twice, output agreed, source deletion failed safely and DB preserved (synthetic data only)'
