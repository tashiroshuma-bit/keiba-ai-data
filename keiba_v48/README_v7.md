# v7 JRA official PDF database importer
The official index pages list graded races and link to playback PDFs.
This package creates a SQLite DB of race metadata, source PDF URLs, SHA256, locally archived PDF files, and extracted **raw PDF text**.

Install: `pip install beautifulsoup4 pdfplumber`
Run on an internet-enabled machine: `python jra_pdf_archive.py --db jra_2023_2025.sqlite --pdf-dir jra_pdfs`
Offline index option: `python jra_pdf_archive.py --index-dir saved_indexes --no-download`
Expected offline files: `saved_indexes/2023.html`, `2024.html`, `2025.html`.

IMPORTANT: PDF text extraction is NOT structured runner-result verification. `runner_results` stays empty until race-by-race parsing and manual or independent reconciliation are implemented. Missing source or PDF extraction failures are recorded. No odds timestamp or real predictive accuracy is implied.

The current ChatGPT container cannot resolve www.jra.go.jp, so this package has not populated the 2023-2025 database. The year pages were separately confirmed available via web browsing.
