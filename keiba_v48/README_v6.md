# v6: point-in-time data integrity
New: `point_in_time.py` with strict pre-race cutoff, race-result publication timestamp, same-race exclusion, and race coverage report. `python -m unittest discover -p 'test_*.py'` runs tests.

Run: `python point_in_time.py --history history.csv --runners runners.csv --output-dir output`

`history.csv`: horse_id,race_id,off_timestamp,result_available_at,finish_position,distance_m,surface.
`runners.csv`: horse_id,race_id,horse_number,off_timestamp,odds_timestamp,pre_off_odds,distance_m,surface,source_url,field_complete.
All times include offsets. `field_complete=yes` is a human attestation, NOT independent proof of a complete field. Results should be stored separately from prediction input.

LIMITATION: No historical real-runner dataset or verified timestamped odds were downloaded in this environment. No v4.8 fitted model or real backtest ROI is claimed. Source: https://www.jra.go.jp/datafile/seiseki/replay/2025/jyusyo.html
