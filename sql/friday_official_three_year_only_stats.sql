-- Historical observed statistics for the SHA-verified subset only.
-- Counts exclude obstacles, unverified race conditions and nonnumerically placed results.
-- Official jockey IDs MUST be available for jockey and horse×jockey totals.
WITH eligible_history AS (
 SELECT * FROM v_archive_observed_starts
 WHERE race_date >= '2023-01-01' AND race_date < '2026-01-01'
), actors AS (
 SELECT 'horse' AS entity,h.horse_id AS entity_id,h.horse_name AS entity_name,
        h.race_id,h.race_date,h.venue_code,h.surface,h.going,h.distance_m,h.wins,h.top3
 FROM eligible_history h
 UNION ALL
 SELECT 'jockey',h.jockey_id,h.jockey_name,h.race_id,h.race_date,h.venue_code,h.surface,h.going,h.distance_m,h.wins,h.top3
 FROM eligible_history h WHERE h.jockey_id LIKE 'jra-jockey:pw04kmk%'
 UNION ALL
 SELECT 'horse_jockey',h.horse_id||'|'||h.jockey_id,h.horse_name||' × '||h.jockey_name,
        h.race_id,h.race_date,h.venue_code,h.surface,h.going,h.distance_m,h.wins,h.top3
 FROM eligible_history h WHERE h.jockey_id LIKE 'jra-jockey:pw04kmk%'
), dimensions AS (
 SELECT a.*, 'all' AS dimension, 'all' AS condition FROM actors a
 UNION ALL SELECT a.*, 'surface',a.surface FROM actors a
 UNION ALL SELECT a.*, 'going',a.going FROM actors a
 UNION ALL SELECT a.*, 'venue',a.venue_code FROM actors a
 UNION ALL SELECT a.*, 'distance_m',CAST(a.distance_m AS TEXT) FROM actors a
 UNION ALL SELECT a.*, 'surface_going',a.surface||'/'||a.going FROM actors a
 UNION ALL SELECT a.*, 'venue_surface',a.venue_code||'/'||a.surface FROM actors a
)
SELECT entity,entity_id,entity_name,dimension,condition,COUNT(*) AS starts,
 SUM(wins) AS wins,SUM(top3) AS top3,
 ROUND(100.0*SUM(wins)/COUNT(*),2) AS win_rate_pct,
 ROUND(100.0*SUM(top3)/COUNT(*),2) AS top3_rate_pct,
 MIN(race_date) first_race_date,MAX(race_date) last_race_date,
 'PARTIAL_SOURCE_COVERAGE_NOT_FULL_CAREER' AS coverage
FROM dimensions
GROUP BY entity,entity_id,entity_name,dimension,condition
ORDER BY entity,entity_id,dimension,condition;
