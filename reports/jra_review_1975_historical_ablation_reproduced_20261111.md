# JRA 要再確認1,975レース・過去レース実データ研究検証（2026-11-11再実行）

## 検証の範囲と正本
- 入力正本v12: Library `/競馬/jra_2023_2025_v12_horse_ids_full_20261111.sqlite`, 362139648 bytes, SHA256 `5d16777588420ac88bab5df21defb85d9346c2b918bb71859af06893752bcadd`; original v12 unchanged.
- Initial 1,975-review overlay: Library `/競馬/jra_review_1975_result_grade_overlay_final_20261111.sqlite`, original SHA256 `7fd4e436f8376e2b271e8df65f9be24047eada992a48fc91a099b993b1938745`.
- Official original JRA result HTML and last 16 missing days: Library `/競馬/jra_original_official_html_evidence_all_47_archives_20261111.zip` and `/競馬/jra_review_missing16_official_source_8archives_20261111.zip`, audited in `/競馬/jra_review_all1975_reconciled_20261111.json`.
- Original JRA 5-PDF archive verifying nine whole-race cancellations: `/競馬/jra_review_nine_cancellations_official_pdf_verified_20261111.zip`; detailed 9-race source URL, page, SHA from `/競馬/jra_review_nine_cancellations_pdf_original_audit_20261111.json`. A fresh independent read of the archived ZIP returned testzip=None, five original PDFs SHA matching the audit, and PyMuPDF page-text contained the correct race number plus 「競走の中止」 for all nine.
- New independent hardened 1,975-race research overlay: `/競馬/jra_review_1975_verified_v2_20261111.sqlite`, **6,254,592 bytes, SHA256 `5f80b199b61b401fb046a0d7c2fb065b8c433dbc5734fcbefb5f0740ae3d03ea`**, quick_check=ok, FK violations=0; original v12 or first overlay NOT changed.
- Reproducible hardening implementation: `scripts/jra_review_evidence_v2.py` with input arguments and explicit immutable output. Evidence audit: `/競馬/jra_review_1975_verified_v2_audit_20261111.json`.

## All 1,975 review races accounted for
| Source and exact state | Races |
|---|---:|
| Official JRA original result HTML, all horse numbers and result labels corroborated | 1,966 |
| Original JRA annual PDF original bytes show whole-race cancellation; no finish labels | 9 |
| Unclassified | **0** |

Within the 1,966 completed racing-result pages:
- 615 official all-numeric, complete-name, metadata-ready races.
- 1,348 races contain special states: **837 DNF + 410 excluded + 264 scratched = 1,511 runner status rows** (some races include multiple status rows), not suitable for naive finish-order training.
- Nine horse-name mismatches in 2023-01-29 Chukyo 12R were exact PDF glyph fourfold repeats. A deterministic 4× glyph-compression produced the exact official names on 9 of 9 horse numbers, including one DNF. The original OCR/PDF names remain preserved in canonical.
- One foreign 2024-11-24 Japan Cup horse #13 **ファンタスティックムーン** had the result HTML displayed name shortened to ファンタスティック. Independent JRA horse profile URL https://www.jra.go.jp/JRADB/accessU.html?CNAME=pw01dud102020190004%2FAF shows official 10-digit ID `jra:2020190004`, 11th finish, 440kg on same race/date; alternate official JRA rating table https://www.jra.go.jp/datafile/ranking/jyusyo/2024/11-g1.html confirms full name and 11th finish.
- 2023-08-20 Sapporo 7R (`202301020407`) missing calendar date and distance was independently confirmed by the JRA official full result at https://www.jra.go.jp/JRADB/accessS.html?CNAME=pw01sde1001202302040720230820%2F13 : turf, 2,000 metres, 16 runners, official original SHA in overlay.
- 9 cancelled: JRA original PDF source verified with 5 SHA-checked original PDFs. These cannot be used to score a winning/placing ranking.
- Another **315 official numerical order discrepancies** in special-rank/tie races were separately recorded. No silent overwrite of canonical original raw `finish_order`.
- Review runner evidence covers **27,154** rows including numerical 25,643, special 1,511. The other 9 whole-race cancellations had no runner result rows.

## Strict historical prediction-research evaluation, exact reproducibility verified
Actual execution command (against true canonical and hardened overlay):
```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python scripts/jra_historical_horse_id_ablation.py \
  --database /path/to/jra_2023_2025_v12_horse_ids_full_20261111.sqlite \
  --review-overlay /path/to/jra_review_1975_verified_v2_20261111.sqlite \
  --output-json /path/to/jra_historical_ablation_reproduced_v2_20261111.json \
  --output-race-csv /path/to/jra_historical_ablation_reproduced_v2_races_20261111.csv
```
Real reproducibility check **passed**: all source-pinned output `models`, `paired_differences`, `top1_calibration`, `features` and `skipped_ambiguous_races` matched the prior saved original experiment results *exactly* (only source overlay SHA and output file hash differ).

This is a matched-learner **horse ID ablation experiment**, **not a v50-v51 actual historical replay**:
- Same fixed 31 horse+jockey+field features, scikit-learn L2 LogisticRegression(C=1), two versions trained only on 2023-24 validated-result races, 5,865 races / 80,547 runner rows. Full ID model sees restored JRA identities; masked comparator artificially conceals IDs originally absent in v11. Model training weights are independently refitted on the *same* 2023-24 cohort per variant.
- Each date freezes all feature rows before adding that date's official results to history, and forbids same-day or future outcomes, historic final odds and race-day bodyweight. **Historic actual publication timestamps remain unknown**; chronological-date reconstruction is a research assumption.
- The evaluation cohort consists of 2025 validated 2,925 races and 2026 validated 2,411 races, no holdout refit.
- An additional 601 eligible 2023-26 reviewed races were included in feature creation; only the **2025 176** and **2026 123** eligible reviewed races were extra holdouts (14 of the 615 all-numeric review races had ambiguous first-place ties and were excluded from single-winner scoring).

### Main validated-result holdouts (same races and feature policy)
| Statistic | 2025 old-ID-mask | 2025 restored-ID | 2026 old-ID-mask | 2026 restored-ID |
|---|---:|---:|---:|---:|
| 1st-choice exact winner | 21.68% (634/2925) | **24.10% (705/2925)** | 21.19% (511/2411) | **24.84% (599/2411)** |
| Actual winner among top 3 | 49.91% | **55.38%** | 47.45% | **55.25%** |
| Exact 3 horses unordered | 3.49% | **5.16%** | 3.61% | **5.64%** |
| Exact 3 ordered | 0.62% | **1.16%** | 0.79% | **1.16%** |
| Average winner log loss | 2.3378 | **2.2331** | 2.3618 | **2.2343** |
| Average multiclass Brier | 0.8871 | **0.8673** | 0.8884 | **0.8666** |

- Pooled exact-winner accuracy 2025+26 across 5,336 holdout races: **1,145/5,336 = 21.46%** masked versus **1,304/5,336 = 24.44%** restored, +159 winners/+2.98 pp.
- Cluster-on-calendar-day bootstrap (3,000 same-year day resamples) 95% CIs for restored−masked top1: 2025 **[+1.14,+3.68] pp**, 2026 **[+2.23,+5.13] pp**. These are in-sample-year resampling intervals, not guaranteed deployment uplift.
- Reviewed-result heldout extra: 2025 176 races **20.45%→19.89%** (slightly worse), log loss 2.3622→2.3065. 2026 123 races **17.07%→17.89%**, log loss 2.3942→2.3310. The rank hit gain is not consistent in this special cohort.
- Top1 ECE calibration on validated holdouts: 2025 **0.05342→0.05326** (unchanged); 2026 **0.05601→0.06577** (**worse**). ID recovery alone does not solve probability calibration.

## What is / isn't completed
- **Complete for the requested scope**: 1,975 review race primary-source classification (9 whole-race cancelled original PDFs verified); 10 name discrepancies with source-graded resolution; 1 missing race metadata; production canonical DB preserved; full historical ID ablation rerun and exact reproducibility.
- **Not completed, must not claim**: official standard v50 versus learned conditional-rank v51 same-race/same-asof prospective or historical preoff A-source comparisons across all holdouts; matching model A historic snapshots are unavailable. The independent logistic ablation is not an approved production model promotion.
- **Implementation policy**: keep production **v50**, **v51 research-only**. Keep special statuses DNF/excluded/scratched distinct instead of casting source row positions to finish ranks, and re-evaluate rank probabilities and calibration on independent actual preoff field observations.
