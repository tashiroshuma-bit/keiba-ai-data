# v4.8 統合状態

現在の正本は [PROJECT_STATE.json](../PROJECT_STATE.json)、作業手順は [DEVELOPMENT_HANDOFF.md](../DEVELOPMENT_HANDOFF.md)。DB version 8、利用可能10,056レース、除外309レース。本番モデルは据え置き、購入生成無効、真の前向き0/100。最新実測は [TIME_EXCEPTION_REPAIR_RESULTS.md](TIME_EXCEPTION_REPAIR_RESULTS.md)。

## 以下は初期取り込み時点の旧記録

- Verified JRA race indexes for 2023, 2024, 2025 (sources.csv).
- Added offline HTML parser for full-field JRA result tables; manual inspection required on any format change.
- Race-result records are **post-race labels only** and cannot be used as predictive features.
- Historical point-in-time odds, pre-race features and runner ID joins have NOT been collected; no valid v4.8 performance estimates yet.
- Environment outbound HTTP/DNS request to JRA failed, so bulk historical collection is blocked here.
- Next: acquire HTML snapshots or permitted CSV exports; run importer and field completeness checks, then join historical starts by stable horse ID, and only then fit chronological baseline.
