WITH ranked AS (
 SELECT e.target_race_id,e.horse_number,h.race_id,h.race_date,h.venue,h.surface,h.going,h.distance_m,h.finish_position,
 ROW_NUMBER() OVER(PARTITION BY e.target_race_id,e.horse_number ORDER BY h.race_date DESC,h.race_id DESC) AS n
 FROM declared_entries e JOIN v_eligible_history h ON h.horse_id=e.horse_id AND h.race_date<e.target_date
)
SELECT * FROM ranked WHERE n<=5 ORDER BY target_race_id,horse_number,n;
