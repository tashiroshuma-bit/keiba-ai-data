# Cloud collection route (GitHub Actions)
1. Create a private GitHub repository. Do not commit your account credentials.
2. Upload the **contents** of this package, retaining `.github/workflows/jra-ingest.yml`.
3. Open GitHub Actions > JRA PDF archive ingest > Run workflow.
4. After it finishes, open the workflow run > Artifacts > `jra-archive-...`.
5. Download the ZIP to retrieve `jra_2023_2025.sqlite`, `jra_pdfs/`, and `ingest_status.json`.
6. The weekly schedule is a retry mechanism. GitHub Actions execution depends on GitHub account limits and website access. Verify results rather than assuming success.
7. PDF text is not verified structured runners; subsequent validation is required. Keep source attribution, respect site terms and rate limits; do not redistribute PDFs without permission.
8. To reuse data across scheduled runs, you must reupload/recover the prior DB/PDF artifact; GitHub Actions runners are ephemeral. The script itself is resumable given those files.
9. If official site blocks GitHub-hosted runners, run the same command on a local PC or another network.
