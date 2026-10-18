# Keiba v4.8: offline, leakage-safe backtest v4

This extends the v3 official-result parser with a real backtest engine, not a trained predictive model.

## Input
`preoff_runners_template.csv` is a schema template. One row per runner. Every runner in a race must be present, with a uniquely identified horse, correct finishing rank and a timestamped pre-off single-win odds snapshot. ISO timestamps must include offsets. `final_win_odds` is the official *settlement* price and is used only for payout of the winner, never to generate probabilities. The `pre_off_score` field is optional and must itself be created only from data available before the race.

## Run
```
python -m unittest -v test_backtest_engine.py test_official_import.py
python backtest_engine.py your_real_preevent_runners.csv --output results.json
```

The baseline is a normalized inverse pre-off odds model; it is **not v4.8 learned parameters**. The optional `--score-field pre_off_score --alpha 0.2` demonstrates scoring but is not fitted. To estimate alpha, fit on a training set and lock it before a separate validation set.

## Caveats
- Do not use final odds as pre-off odds. No data means no measured backtest.
- Only exact unambiguous finishing orders are supported; dead heats, scratches, non-finishers, and missing runners are excluded, not silently scored.
- Rank probabilities, pair top-three and triple top-three are calculated, but pair/triple EV cannot be computed without authentic timestamped pair/triple betting prices.
- Race-level metrics are log loss, multi-runner Brier score, top pick hit rate, and single win baseline return where final settlement is available. ROI for v4.8 has not been established.
- JRA result pages can be collected separately with permission and validated by `official_import.py`; their race results are labels, not predictors.
