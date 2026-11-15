-- Five most recent real flat starts for each official horse ID in 2023–2025 only.
-- All rows have race source SHA and official race ID; cancelled/absent starters excluded.
WITH ranked AS (
 SELECT horse_id,horse_name,race_date,race_id,venue_code,race_number,surface,going,distance_m,
  placing,jockey_name,jockey_id,wins,top3,
  ROW_NUMBER() OVER(PARTITION BY horse_id ORDER BY race_date DESC,race_id DESC) AS recency_rank
 FROM v_archive_observed_starts
 WHERE race_date >= '2023-01-01' AND race_date < '2026-01-01'
)
SELECT horse_id,horse_name,recency_rank,race_date,race_id,venue_code,race_number,
 surface,going,distance_m,placing,jockey_name,jockey_id,wins,top3
FROM ranked WHERE recency_rank <=5 ORDER BY horse_id,recency_rank;
