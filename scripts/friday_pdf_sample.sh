#!/usr/bin/env bash
# Read a single official JRA PDF to prove parser layout. Not an all-year import.
set -euo pipefail
out=reports/friday_full_backfill/sample
mkdir -p "$out"
command -v pdftotext >/dev/null || { echo 'Install poppler-utils'; exit 2; }
src='https://www.jra.go.jp/datafile/seiseki/report/2025/2025-5tokyo1.pdf'
curl --fail --silent --show-error --location --max-redirs 0 --retry 1 --max-time 40 --user-agent 'JRA-History-Audit/1.0' "$src" -o "$out/2025-5tokyo1.pdf"
head -c 5 "$out/2025-5tokyo1.pdf" | grep -aq '%PDF-' || { echo 'NOT_READY: invalid PDF'; exit 2; }
sha256sum "$out/2025-5tokyo1.pdf" > "$out/sample.sha256"
pdfinfo "$out/2025-5tokyo1.pdf" | head -n 12 > "$out/pdfinfo.txt"
pdftotext -layout -enc UTF-8 "$out/2025-5tokyo1.pdf" "$out/layout.txt"
pdftotext -raw -enc UTF-8 "$out/2025-5tokyo1.pdf" "$out/raw.txt"
pdfinfo "$out/2025-5tokyo1.pdf" | grep -q '^Pages: *[6-9]' || { echo 'UNEXPECTED_PAGE_COUNT'; exit 2; }
grep -q '第1' "$out/raw.txt" || { echo 'NOT_READY: 1R unrecognized'; exit 2; }
echo 'SAMPLE_PDF_SHA:'; cat "$out/sample.sha256"
echo 'SAMPLE_LAYOUT_FIRST_80_LINES:'; sed -n '1,80p' "$out/layout.txt"
echo 'SAMPLE_RAW_FIRST_55_LINES:'; sed -n '1,55p' "$out/raw.txt"
