-- Usage: sqlite3 -readonly -header -csv history.sqlite < sql/friday_report.sql > report.csv
-- Only observed historical results strictly before each target date; no inferred values.
WITH
 eligible AS (
 SELECT e.*,h.race_id AS history_race_id,h.surface,h.going,h.venue AS history_venue,h.distance_m,h.win,h.top3
 FROM declared_entries e LEFT JOIN v_eligible_history h
   ON h.horse_id=e.horse_id AND h.race_date < e.target_date
 ),
 horse AS (
 SELECT target_race_id,horse_number,COUNT(history_race_id) starts,
 SUM(CASE WHEN history_race_id IS NOT NULL THEN win ELSE 0 END) wins,
 SUM(CASE WHEN history_race_id IS NOT NULL THEN top3 ELSE 0 END) top3
 FROM eligible GROUP BY target_race_id,horse_number
 ),
 jockey AS (
 SELECT e.target_race_id,e.horse_number,COUNT(h.race_id) starts,
 COALESCE(SUM(h.win),0) wins,COALESCE(SUM(h.top3),0) top3
 FROM declared_entries e LEFT JOIN v_eligible_history h
 ON h.jockey_id=e.jockey_id AND h.race_date < e.target_date
 GROUP BY e.target_race_id,e.horse_number
 ),
 joint AS (
 SELECT e.target_race_id,e.horse_number,COUNT(h.race_id) starts,
 COALESCE(SUM(h.win),0) wins,COALESCE(SUM(h.top3),0) top3
 FROM declared_entries e LEFT JOIN v_eligible_history h
 ON h.jockey_id=e.jockey_id AND h.horse_id=e.horse_id AND h.race_date < e.target_date
 GROUP BY e.target_race_id,e.horse_number
 )
SELECT e.target_date,e.venue,e.race_number,e.horse_number,e.horse_name,e.horse_id,e.jockey_name,e.jockey_id,
 h.starts horse_starts,h.wins horse_wins,h.top3 horse_top3,
 CASE WHEN h.starts>0 THEN ROUND(100.0*h.wins/h.starts,2) END horse_win_pct,
 CASE WHEN h.starts>0 THEN ROUND(100.0*h.top3/h.starts,2) END horse_top3_pct,
 j.starts jockey_starts,j.wins jockey_wins,j.top3 jockey_top3,
 CASE WHEN j.starts>0 THEN ROUND(100.0*j.wins/j.starts,2) END jockey_win_pct,
 CASE WHEN j.starts>0 THEN ROUND(100.0*j.top3/j.starts,2) END jockey_top3_pct,
 x.starts pair_starts,x.wins pair_wins,x.top3 pair_top3,
 CASE WHEN x.starts>0 THEN ROUND(100.0*x.wins/x.starts,2) END pair_win_pct,
 CASE WHEN x.starts>0 THEN ROUND(100.0*x.top3/x.starts,2) END pair_top3_pct
FROM declared_entries e
JOIN horse h USING(target_race_id,horse_number)
JOIN jockey j USING(target_race_id,horse_number)
JOIN joint x USING(target_race_id,horse_number)
ORDER BY e.target_date,e.venue,e.race_number,e.horse_number;
