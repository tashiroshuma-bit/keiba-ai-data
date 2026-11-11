# JRA horse ID source-backed recovery — 2026-11-11

## Decision
PARTIAL VERIFIED RECOVERY. Production forecast v50 and research v51 unchanged. Canonical v11 read-only, no horse IDs guessed, no production DB overwrite.

## Verified inputs
- Canonical Library `/jra_2023_2025.sqlite`, 322170880 bytes, SHA256 `7206c787e6b13616e0ac1a0950d31a2539188c466fd369bdcd916f4f58f59627` measured.
- Starting checkpoint `/競馬/horse_id_overlay_jra_bulk_checkpoint_21925_20261110.sqlite`: 21003 direct, 922 profile candidate, 44435 missing.
- Source archives from Actions run 42780017487 (2023–25), run 42780335360 (2026), and 2026 week42 existing Library original. Source ZIPs retained in Library /競馬; JRA original bytes NOT committed to GitHub.
- `scripts/jra_reconcile_official_source_archives.py` on main verifies each original HTML SHA256, manifest, horse number/name/10-digit JRA ID and canonical race/date; fails closed on conflicts.

## Measured result
- 2023–25 shards 9–23, 2026 shards 0,3–7 and additional shard 8 plus week42 were incrementally reconciled against the read-only canonical v11 and prior overlay.
- New direct rows in successive passes: 1562 + 7463 + 8539 + 12611 + 7462 + 1730 = **39367**. Starting direct 21003, final direct **60370**.
- Final covered **60483** (60370 direct + 113 profile corroborated candidate), out of **66360** original canonical NULL rows.
- **5877** rows have no candidate, **5990** remain without direct official confirmation.
- Remaining reason in audit: `official_source_page_not_yet_observed` (5877). No fabricated IDs.
- Final sidecar: Library `/競馬/horse_id_overlay_jra_bulk_checkpoint_60483_20261111.sqlite` size **32538624 bytes**, SHA256 **d8e3864e3494d12c78903421f0176d6c1f381c63dbf262ba96898ebab882c383**. Verified SHA256 and SQLite quick_check=ok **after Library upload and readback**.
- Audit: `/競馬/horse_id_overlay_jra_bulk_checkpoint_60483_audit_20261111.json`; unresolved and rejection CSVs saved alongside.
- Source artifact retention: 2023–25 shards 8–23 and 2026 shards 0,3–7 uploaded to Library; previous 2023–25 shards 0–7 and 2026 shards 1–2 already present.

## Limitations / next action
The 5877 remaining rows cannot be safely filled without new verified JRA source pages. The old v10 figure 77317 and canonical v11 66360 are different populations and must not be subtracted. This sidecar is research/evidence only; no canonical mutation or v50 retraining, freeze, settle or purchase. Source collection and name/number conflict investigation must continue.
