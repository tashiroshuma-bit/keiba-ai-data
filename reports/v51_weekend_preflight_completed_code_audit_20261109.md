# 2026-11-14/15 JRA v50/v51 preflight and research implementation evidence

Recorded: 2026-11-09 JST. **v50 remains officially standard. v51 is research only.**

## Delivered improvements and CI
| Feature | Source | Tests and limits |
|---|---|---|
| Official ID recovery P0 | [v51_identity_sidecar.py](../../scripts/v51_identity_sidecar.py) | [CI 42609482304](https://github.com/tashiroshuma-bit/keiba-ai-data/actions/runs/42609482304) passed. Requires official per-race evidence source bytes and identifiers; **0 real IDs newly demonstrated**. No alteration of canonical SQLite or fuzzy name joins. |
| Conditional 2nd/3rd P0 | [v51_conditional_rank_pair_evaluation.py](../../scripts/v51_conditional_rank_pair_evaluation.py), existing `keiba_v48/rank_forecast.py` | [CI 42610294175](https://github.com/tashiroshuma-bit/keiba-ai-data/actions/runs/42610294175) passed. Compares separately learned rank shadow p1/p2/p3 & podium picks against SAME-FORECAST-PAIRED v50 fields. **0 genuine prospective paired comparisons yet**. Research PL triplet baseline in `v51_research_diagnostics.py` is not a fitted conditional model. |
| Horse form/class/opponent P1, jockey course/distance P1, prior race track bias P2, rest/bodyweight P2 | [v51_preoff_feature_builder.py](../../scripts/v51_preoff_feature_builder.py) | [CI 42609949304](https://github.com/tashiroshuma-bit/keiba-ai-data/actions/runs/42609949304) passed after fixing race-day date classification to JST, not UTC. Historical feature sources must have exact horse ID proof and be observed at/before asof; unknowns remain missing. Actual feature population and model training NOT demonstrated. |
| Probability confidence/calibration P2 | [v51_calibration_audit.py](../../scripts/v51_calibration_audit.py) | [CI 42610569599](https://github.com/tashiroshuma-bit/keiba-ai-data/actions/runs/42610569599) passed. Measures top1 probability vs actual hit per bucket and high-entropy race; no refitting/evaluated improvement claim. |
| Preoff source verification P0 | [capture_v50_bodyweight.py](../../scripts/capture_v50_bodyweight.py), [v51_weekend_preflight.py](../../scripts/v51_weekend_preflight.py) | [CI 42608901190](https://github.com/tashiroshuma-bit/keiba-ai-data/actions/runs/42608901190) passed. Immutable archive refuses missing/tampered original source bytes, bad SHA, after-off time, wrong roster. **Stored original byte hash does not by itself independently prove capture time/publication**. |

Completed and merged PRs: [#5](https://github.com/tashiroshuma-bit/keiba-ai-data/pull/5), [#6](https://github.com/tashiroshuma-bit/keiba-ai-data/pull/6), [#7](https://github.com/tashiroshuma-bit/keiba-ai-data/pull/7), [#8](https://github.com/tashiroshuma-bit/keiba-ai-data/pull/8), [#9](https://github.com/tashiroshuma-bit/keiba-ai-data/pull/9). Last merge `115db8915e23f3b4272d97ece3491657e2320212`. All listed CI runs' test and legacy-diagnostics jobs passed before merge.

## Critical hard blockers that code tests cannot resolve
1. True canonical SQLite Library v11 must actually be materialized during the scheduled runner and hashed to PROJECT_STATE. The GitHub repository's namesake SQLite is an ingestion stub, NOT the canonical 322MB DB. `v51_weekend_preflight.py` must fail `NOT_READY` without DB.
2. Real full-field **source A** preoff generator must execute and save all horses and their actual source snapshots. GitHub repo tests use synthetic/source-file fixtures and cannot guarantee a live source feed, access privileges or rate limits. Standard `standard_v50_forecast.py` **requires** this, and cannot fabricate.
3. Real body weight for the same race field becomes public only when announced. Save exact original response/document bytes to `<sha256>.bin`, true observed_at, URL and a full horse-number-matched weight JSON. Pass `--weight-source-archive` to `capture_v50_bodyweight.py`. Refuse retrospective post-off rebranding as preoff.
4. Hourly automation checks are NOT sufficient to guarantee capturing all 36 races; per-race weigh-ins and access timing may not align with hourly checks. A reliable 5-15 minute external acquisition service is not established in this repo. No guaranteed 100%-race capture statement.
5. For result settlement, full official finishing order and unambiguous result provenance are required, otherwise exclude and record race IDs.
6. Historical 2025/2026 cohorts were previously inspected; actual independent evidence starts with *new* prospective preoff captures. Two racing days have limited effective independent sampling for promotion.

## Weekend tasks
Active automation IDs:
- `Automation_0c00494ce4ac819190eed9d1547482ec`: Friday preflight 2026-11-13 around 21:00 JST;
- `Automation_39cb759d3d688191b97d9abda2e623e8`: hourly preoff monitoring Sat/Sun 2026-11-14/15 ~09:00-16:00 JST;
- `Automation_998ded01d4508191afbe20a6a2271362`: official result paired assessment Sat/Sun ~19:00 JST.
Prompts updated to require archived original source bytes, `--weight-source-archive`, strict source A match and accurate failure counts. Automated schedule is not evidence of success until each run reports actual artifacts and SHA readback.

## Completion criteria
Do not infer v51 uplift from synthetic CI. Record for each official race: attempted, preoff source available, all runners, weight announcement, original source timestamp/bytes/digest, v50 forecast generated and immutable saved, v51 research shadow and genuine learned podium shadow, official result, actual metrics. Publish **numerator and denominator** and all exclusion reasons. Treat no prospective records as **no claim** rather than a zero hit rate.

Do not promote v51 based on P1/P2 code readiness. It remains a research branch pending genuine source evidence, fit, selection, and unseen comparison; keep existing v50 routes unchanged.
