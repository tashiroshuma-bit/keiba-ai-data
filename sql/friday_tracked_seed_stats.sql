-- Actual, bounded JRA-derived Git-source retrospective profile statistics.
-- No jockey IDs: horse-only. Do NOT promote to complete Friday result report.
WITH profile AS (
  SELECT horse_id,horse_name,prior_race_date,
         CASE WHEN distance_surface LIKE '芝%' THEN '芝'
              WHEN distance_surface LIKE 'ダート%' THEN 'ダート' ELSE '不明' END AS surface,
         going,finish_position
  FROM tracked_profile_past_run
), totals AS (
  SELECT 'horse_all' category,horse_id,horse_name,'ALL' condition,
         COUNT(*) past_rows,COUNT(finish_position) known_finishes,
         SUM(CASE WHEN finish_position=1 THEN 1 ELSE 0 END) wins,
         SUM(CASE WHEN finish_position BETWEEN 1 AND 3 THEN 1 ELSE 0 END) top3
  FROM profile GROUP BY horse_id,horse_name
  UNION ALL
  SELECT 'horse_surface_going',horse_id,horse_name,surface||'/'||COALESCE(going,'不明'),
         COUNT(*),COUNT(finish_position),
         SUM(CASE WHEN finish_position=1 THEN 1 ELSE 0 END),
         SUM(CASE WHEN finish_position BETWEEN 1 AND 3 THEN 1 ELSE 0 END)
  FROM profile GROUP BY horse_id,horse_name,surface,going
)
SELECT category,horse_id,horse_name,condition,past_rows,known_finishes,wins,top3,
 CASE WHEN known_finishes>0 THEN ROUND(100.0*wins/known_finishes,2) END win_pct_known,
 CASE WHEN known_finishes>0 THEN ROUND(100.0*top3/known_finishes,2) END top3_pct_known,
 'RETROSPECTIVE_DERIVED_SOURCE_JOCKEY_ID_NOT_VERIFIED' status
FROM totals ORDER BY category,horse_id,condition;
