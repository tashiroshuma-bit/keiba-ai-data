# v4.8 official-free ingestion status
- Verified JRA race indexes for 2023, 2024, 2025 (sources.csv).
- Added offline HTML parser for full-field JRA result tables; manual inspection required on any format change.
- Race-result records are **post-race labels only** and cannot be used as predictive features.
- Historical point-in-time odds, pre-race features and runner ID joins have NOT been collected; no valid v4.8 performance estimates yet.
- Environment outbound HTTP/DNS request to JRA failed, so bulk historical collection is blocked here.
- Next: acquire HTML snapshots or permitted CSV exports; run importer and field completeness checks, then join historical starts by stable horse ID, and only then fit chronological baseline.
