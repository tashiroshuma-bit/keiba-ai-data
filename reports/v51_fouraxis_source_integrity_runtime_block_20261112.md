# V51 14-feature real run status — 2026-11-12

## Verified in this run
- Library canonical v12 materialized: 362139648 bytes; SHA256 `5d16777588420ac88bab5df21defb85d9346c2b918bb71859af06893752bcadd`; SQLite quick_check=ok.
- Review overlay materialized: 6254592 bytes; SHA256 `5f80b199b61b401fb046a0d7c2fb065b8c433dbc5734fcbefb5f0740ae3d03ea`; SQLite quick_check=ok.
- Both opened in the same local Python environment, read-only.
- Yearly raw runner row counts 2023:47672; 2024:47181; 2025:47884; 2026:38608. Raw horse ID nonnull (runner/identity link coalesce) 45424,44836,44911,35217 respectively. These are raw schema counts, NOT four-axis feature availability.
- GitHub main source inspected via GitHub connector; local `git clone` failed with `Could not resolve host: github.com`. Hence the exact committed scripts were not executable in the local environment. No substitute study was passed off as the prescribed pipeline.
- Full `scripts/v51_fouraxis_complete_real_run.py` NOT executed; 2025 new-14-feature results, 2025 594R gate, 2026 2411R audit, paired CI, LL/Brier/ECE all NOT computed in this run.
- Baselines unchanged: 2025 719/2925, late 149/594; 2026 603/2411. No production model/policy changed.
- Local read-only audit JSON saved to Library `/競馬/v51_fouraxis_v12_source_integrity_20261112.json`. It is not a canonical coverage or rank experiment result.

## Blocker and next operation
The exact repository code must be made available in the same Python runtime as the already verified Library files (GitHub network DNS is unavailable there). Then run the previously merged `scripts/v51_fouraxis_complete_real_run.py` with v12, review overlay, historical feature script and standard V51 model. Accept only if real 2025 late-period paired date-block CI lower bound >0, Log Loss improves, Brier and ECE do not worsen. Otherwise retain official V51.
