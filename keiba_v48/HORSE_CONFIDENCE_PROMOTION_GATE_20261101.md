# Horse-confidence promotion gate (research only)

Frozen candidate: log(p1) + 0.8 * ((wins + 0.5*seconds + 0.25*thirds + 1.2)/(starts+8) - 0.15). Tie break ascending horse number. Inputs must be pre-race saved career totals.

## Retrospective comparison

- 2026-11-01: baseline D 9/23 (39.13%); candidate 10/23 (43.48%). Candidate changed Tokyo 11R, Kyoto 9R and Kyoto 11R; only Kyoto 9R added a winner.
- Separate date 2026-10-31: five-race saved JOCKEY_OVERLAY_VERIFIED_20261031.json cohort (Kyoto 3R, Tokyo 3R, Tokyo 7R, Kyoto 9R, Tokyo 10R) versus review_20261031/scores.json model D: baseline 2/5 (40%); candidate 2/5 (40%). All five top picks unchanged.
- The five-race subset is NOT the full 23-race October 31 cohort. Both dates are already inspected, not unseen validation.

## Decision

Candidate frozen as research rule. Production promotion gate NOT PASSED: unchanged five predictions do not establish independent-date improvement. AGENTS.md assigns production changes to single-writer implementation/revalidation. Preserve v49 and original forecasts.

## Next research

1. Evaluate the full saved October 31 pre-race roster and D probabilities, including paired hits and every changed pick.
2. Split horse ability by surface, distance, track and opponent class with sample shrinkage and explicit missingness.
3. Estimate rider residual against pre-race horse ability within each historical field; separate surface/distance/course and shrink sparse groups.
4. Require reproducibility and non-degradation before production promotion; never tune on evaluation dates.
