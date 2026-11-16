#!/usr/bin/env bash
set -euo pipefail
temp="$(mktemp -d)"
trap 'rm -rf "$temp"' EXIT
node scripts/friday_mobile_report.mjs preview tests/fixtures/friday_mobile_milecs_registered8_20261116.csv "$temp/preview"
test -f "$temp/preview/INDEX.md"
test -f "$temp/preview/2026-11-22_京都_11R.md"
grep -Fq 'エンブロイダリー' "$temp/preview/2026-11-22_京都_11R.md"
grep -Fq '**62.5%** (5/8)' "$temp/preview/2026-11-22_京都_11R.md"
grep -Fq '**100%** (3/3)' "$temp/preview/2026-11-22_京都_11R.md"
grep -Fq '未照合' "$temp/preview/2026-11-22_京都_11R.md"
grep -Fq '登録段階の表示例' "$temp/preview/2026-11-22_京都_11R.md"
mkdir -p "$temp/status"
printf 'NOT_READY: official Saturday/Sunday entry roster absent\n' > "$temp/status/status.txt"
printf 'year,result_races,officially_cancelled,scheduled_races\n2023,3456,0,3456\n2024,3454,2,3456\n2025,3455,1,3456\n' > "$temp/status/scheduled_coverage.csv"
node scripts/friday_mobile_report.mjs status "$temp/status"
grep -Fq '公式出馬表の照合待ち' "$temp/status/INDEX.md"
grep -Fq '| 2024 | 3454 | 2 | 3456 |' "$temp/status/INDEX.md"
! grep -q '2026-11-22 京都11R' "$temp/status/INDEX.md"
echo 'PASS: mobile-first 2-section per-race preview; missing identity and no-start markers; status fallback'
