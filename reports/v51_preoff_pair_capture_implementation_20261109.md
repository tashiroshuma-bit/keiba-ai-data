# 発走前v50・馬体重のペア保存実装（2026-11-09）

## Status
- Standard future forecast remains **v50**. V51 stays shadow / research, no real-money bet generation, no model promotion.
- Added `scripts/capture_v50_bodyweight.py` with fail-closed immutable archive and strict input integrity requirements.
- Added `tests/test_capture_v50_bodyweight.py` and registered it, body weight audit and shadow tests in `.github/workflows/main.yml`.
- GitHub commits of implementation: `77d0510`, `cf80a93`, tests `5d5591a`, CI `395f115`.
- **No actual post-implementation real race has been archived or settled in this work.** GitHub CI completion not independently observed; do not claim passing checks yet.
- Primary V51 promotion blockers remain: authenticated pre-off weight publication, full v50 production forecasts, genuinely independent prospective paired accuracy comparison.

## Usage
1. Run official `scripts/standard_v50_forecast.py` with canonical DB and **genuine timestamped preoff A forecast input**, saving the exact v50 output.
2. Capture and archive source evidence for full-field weights *before* the same forecast as-of. Explicitly include missing/debut weights as null.
3. Provide original A forecast input, v50 output, and pre-off weight JSON:
```bash
python -m scripts.capture_v50_bodyweight \
  --forecast-source operations/preoff/source_A_20261114.json \
  --v50 operations/predictions/2026-11-14/standard_v50.json \
  --weights operations/preoff/weight_20261114.json \
  --output-dir operations/predictions/2026-11-14
```
4. File `v50_weight_pair_<UTC asof>_<v50 source file sha-prefix>.json` uses exclusive file creation (no overwrite), contains every runner's v50_p1, weight, change and explicit unknowns, asof, original off, input hashes, canonical DB and v50 policy hashes, source provenance.
5. Run `python -m unittest discover -s tests -p 'test_capture_v50_bodyweight.py' -v` and `python -m unittest discover -s tests -p 'test_v51_body_weight_shadow.py' -v`, and CI.

## Weight JSON example (illustrative synthetic values, NOT a real race)
```json
{
  "asof":"2026-11-14T09:00:00+09:00",
  "races":[{
    "race":"2026-11-14 Tokyo 1R",
    "original_off_at":"2026-11-14T10:00:00+09:00",
    "observed_at":"2026-11-14T08:59:00+09:00",
    "source_url":"https://EXAMPLE-ONLY.invalid/official-evidence",
    "source_sha256":"eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
    "horses":[
      {"number":1,"body_weight_kg":480,"weight_change_kg":-4,"weight_observed_at":"2026-11-14T08:59:00+09:00"},
      {"number":2,"body_weight_kg":null,"weight_change_kg":null,"weight_observed_at":"2026-11-14T08:59:00+09:00"},
      {"number":3,"body_weight_kg":500,"weight_change_kg":10,"weight_observed_at":"2026-11-14T08:59:00+09:00"}
    ]
  }]
}
```
All runners must be listed, not just the 3 shown here. The source URL/SHA in a weight manifest is **provided evidence metadata**, not by itself independently authenticated publication proof. For true independent evidence, store the complete underlying source file/snapshot separately and verify its hash and capture timestamp at source ingest. A retroactively provided timestamp must never be accepted as independently verifiable pre-off proof.

## Integrity gates
- Exact A forecast file SHA256 must match hash embedded by v50.
- Complete original v50 race IDs and horse roster must match weights; original off times must agree.
- Weight observation <= forecast asof < race off; no future data.
- Strict numeric weight range 300–650kg or explicit null; unknown delta retained as separate bucket.
- Win probabilities finite, positive, sum to 1 within tolerance.
- Forbid duplicate races/horses, incomplete fields, missing source URL/sha, duplicate destination output.
- No new v50 probability, official prediction router, policy or active model modification.

## Research decision
When genuine prospective same-asof saved records and results are available, compute **paired** 1st-choice, winner-in-top3, exact ordered/unordered podium, per-race logloss/brier and racing-day bootstrap. Promote V51 only with independent measured gain and confirmed provenance. Not from the bodyweight-only historical comparator.

## Caveat
This is a deterministic **capture adapter** rather than an automatic external data crawler or working scheduled end-to-end integration. Without a preoff A-input generator and authentic captured body-weight feed, the archive CLI cannot generate real future races autonomously.
