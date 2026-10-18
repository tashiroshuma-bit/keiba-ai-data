# v9 bulk ingest
Command on an internet-enabled machine:
`python bulk_ingest.py --db jra_2023_2025.sqlite --pdf-dir jra_pdfs --workers 2`
Resume: same command; successfully extracted PDFs are skipped. `--retry-errors` retries failed PDFs.
`--index-dir indexes` reads `2023.html`, `2024.html`, `2025.html` locally instead of fetching indexes.
Limits: up to 4 workers, SQLite writes serialized; official site terms and server load must be respected.

IMPORTANT: race index ingestion and raw PDF text are **not** verified horse-level records. Horse-level PDF parser remains to be developed/validated. Final odds cannot be treated as timestamped pre-race odds. Container outbound JRA DNS unavailable, so archive was not filled here.
