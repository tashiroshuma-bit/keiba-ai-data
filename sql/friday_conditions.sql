-- Condition-specific observed starts: horse, jockey, horse×jockey.
-- For each target runner, only results strictly before target date.
WITH dimensions AS (
 SELECT 'surface' AS dimension, surface AS value, * FROM v_eligible_history
 UNION ALL SELECT 'going', going, * FROM v_eligible_history
 UNION ALL SELECT 'surface_going', surface||'/'||going, * FROM v_eligible_history
 UNION ALL SELECT 'venue', venue, * FROM v_eligible_history
 UNION ALL SELECT 'distance_m', CAST(distance_m AS TEXT), * FROM v_eligible_history
), identities AS (
 SELECT 'horse' entity,e.target_race_id,e.horse_number,e.target_date,e.horse_id AS entity_id,e.jockey_id FROM declared_entries e
 UNION ALL SELECT 'jockey',e.target_race_id,e.horse_number,e.target_date,e.jockey_id,e.jockey_id FROM declared_entries e
 UNION ALL SELECT 'pair',e.target_race_id,e.horse_number,e.target_date,e.horse_id,e.jockey_id FROM declared_entries e
)
SELECT i.target_race_id,i.horse_number,i.entity,d.dimension,d.value,
 COUNT(*) starts,SUM(d.win) wins,SUM(d.top3) top3,
 ROUND(100.0*SUM(d.win)/COUNT(*),2) win_pct,
 ROUND(100.0*SUM(d.top3)/COUNT(*),2) top3_pct
FROM identities i JOIN dimensions d ON d.race_date<i.target_date AND
 ((i.entity='horse' AND d.horse_id=i.entity_id)
 OR (i.entity='jockey' AND d.jockey_id=i.entity_id)
 OR (i.entity='pair' AND d.horse_id=i.entity_id AND d.jockey_id=i.jockey_id))
GROUP BY i.target_race_id,i.horse_number,i.entity,d.dimension,d.value
ORDER BY i.target_race_id,i.horse_number,i.entity,d.dimension,d.value;
