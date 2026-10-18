# v11: bulk PDF audit and atomic promotion
1. Run `python bulk_ingest.py --db ../jra_2023_2025.sqlite --pdf-dir ../jra_pdfs --workers 2` in an environment with access to JRA.
2. Run `python verify_and_promote.py --db ../jra_2023_2025.sqlite` to audit extracted text.
3. Independently verify all runners against official results and the field size. Promote individual reviewed races with `--year 2025 --race-key 001 --expected-count 18`.

Important: ready_for_review is not verified. No additional real PDFs have been fetched. The original database still contains only 2025 Nakayama Kimpai 18 runners. Never treat final odds as timestamped pre-race odds.
