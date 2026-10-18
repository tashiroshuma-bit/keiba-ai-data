# v10 - All-race extraction pipeline work
- Added conservative PDF runner line parser with strict duplicate/count audit.
- Tested with real official 2025 Nakayama Kimpai PDF text line.
- Existing database retains 1 race / 18 runners; no additional actual PDF files were downloaded in this execution.
- IMPORTANT: PDF parser is an initial implementation, not validated across 2023-2025 variations. Horse number glyph variants, disqualifications, dead heats, jockey name spaces and missing odds require more fixtures. Do not bulk-write unverified rows.
- Run archive ingestion on a machine with outbound JRA access: `python keiba_v48/bulk_ingest.py --db jra_2023_2025.sqlite --pdf-dir jra_pdfs --workers 2`.
