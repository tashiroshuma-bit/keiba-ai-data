# V52 Joint PL source-integrity and runtime audit — 2026-11-16

## Verified in this run
- Library canonical v12 `jra_2023_2025_v12_horse_ids_full_20261111.sqlite`: 362139648 bytes, SHA256 `5d16777588420ac88bab5df21defb85d9346c2b918bb71859af06893752bcadd`, SQLite `PRAGMA quick_check=ok`.
- Library review overlay `jra_review_1975_verified_v2_20261111.sqlite`: 6254592 bytes, SHA256 `5f80b199b61b401fb046a0d7c2fb065b8c433dbc5734fcbefb5f0740ae3d03ea`, SQLite `PRAGMA quick_check=ok`.
- Both private files were materialized in the same Python environment and read without modification.
- `PROJECT_STATE.json` fetched from GitHub main: `standard_forecast.version=v51`, `no_fallback_to_v50=true`.

## Blocker and release decision
GitHub main source files are readable through the GitHub connector, but the Python execution environment cannot resolve `api.github.com` and `container.exec` returns `ClientError`. The complete dependency tree for `scripts/v51_joint_pl_real_2025_study.py` was therefore not installed in the Python environment. The genuine Joint PL training, 2025 temporal comparison, 2026 post-selection audit and pre-off 45-feature smoke were **not executed** in this run. No learned 3x71 coefficients or V52 accuracy metrics were produced. GitHub CI success must not be treated as empirical model performance.

**Decision: V52 promotion gate NOT PASSED; keep production V51 unchanged.** No private DB was uploaded to GitHub. No betting enabled.

Machine-readable source receipt: Library `/競馬/v52_source_integrity_20261116.json`.
