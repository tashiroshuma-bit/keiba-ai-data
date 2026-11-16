-- 2026-11-22 Mile Championship (Kyoto 11R) registered-runner analysis.
-- PROVISIONAL: entrants from 2026-11-16 JRA official G1 information;
-- the eight odds/jockey indications are from a user-supplied netkeiba screenshot.
-- Official final JRA declaration is scheduled for 2026-11-19. NOT an official racecard.
-- All observed results below come from the persisted SHA-tested JRA HTML replay database.
CREATE TEMP TABLE registered (
 candidate_order INTEGER PRIMARY KEY,
 horse_name TEXT NOT NULL,
 screenshot_provisional_jockey TEXT,
 screenshot_predicted_win_odds REAL
);
INSERT INTO registered VALUES
(1,'エンブロイダリー','ルメール',3.4),
(2,'ロデオドライブ','モレイラ',4.8),
(3,'ワールズエンド','Cデム',9.1),
(4,'アドマイヤズーム','武豊',10.3),
(5,'スターアニス','松山',10.5),
(6,'ガイアフォース','西村淳',11.7),
(7,'エルデナリ','バルザ',18.4),
(8,'シックスペンス','プーシャン',20.5),
(9,'アンパドゥ',NULL,NULL),
(10,'ウォーターリヒト',NULL,NULL),
(11,'エコロアルバ',NULL,NULL),
(12,'エコロブルーム',NULL,NULL),
(13,'オフトレイル',NULL,NULL),
(14,'ココナッツブラウン',NULL,NULL),
(15,'ジューンテイク',NULL,NULL),
(16,'スズハローム',NULL,NULL),
(17,'ドラゴンブースト',NULL,NULL),
(18,'ピコローズ',NULL,NULL),
(19,'マジックサンズ',NULL,NULL),
(20,'レザベーション',NULL,NULL),
(21,'レッドシュヴェルト',NULL,NULL);

CREATE TEMP VIEW registered_id AS
 SELECT e.*, COUNT(DISTINCT s.horse_id) AS official_horse_ids_found,
        CASE WHEN COUNT(DISTINCT s.horse_id)=1 THEN MIN(s.horse_id) END AS official_horse_id
 FROM registered e LEFT JOIN archive_runners s ON s.horse_name=e.horse_name
 GROUP BY e.candidate_order;

-- Group by a real official horse ID, not an inferred/name-only identity.
CREATE TEMP VIEW registered_observed_starts AS
 SELECT e.candidate_order,e.horse_name,e.official_horse_id,
        s.race_date,s.race_id,s.venue_code,s.surface,s.going,s.distance_m,
        s.placing,s.wins,s.top3,s.jockey_name,s.jockey_id
 FROM registered_id e
 LEFT JOIN v_archive_observed_starts s ON s.horse_id=e.official_horse_id
  AND s.race_date<'2026-11-16'
 WHERE e.official_horse_ids_found=1;

.headers on
.mode csv
.once reports/milecs_20261122/registered_21_horse_history.csv
SELECT e.candidate_order,e.horse_name,e.official_horse_ids_found,e.official_horse_id,
 CASE WHEN e.official_horse_ids_found=1 THEN 'MATCHED_JRA_HORSE_ID'
      WHEN e.official_horse_ids_found=0 THEN 'NO_VERIFIED_JRA_HISTORY_FOREIGN_OR_OTHER'
      ELSE 'AMBIGUOUS_OFFICIAL_HORSE_IDS' END identity_status,
 e.screenshot_provisional_jockey,e.screenshot_predicted_win_odds,
 COUNT(s.race_id) FILTER (WHERE s.race_date<'2026-01-01') AS starts_2023_2025,
 COALESCE(SUM(s.wins) FILTER (WHERE s.race_date<'2026-01-01'),0) AS wins_2023_2025,
 COALESCE(SUM(s.top3) FILTER (WHERE s.race_date<'2026-01-01'),0) AS top3_2023_2025,
 COUNT(s.race_id) FILTER (WHERE s.race_date<'2026-01-01' AND s.surface='芝' AND s.distance_m=1600) AS turf1600_starts_3y,
 COALESCE(SUM(s.wins) FILTER (WHERE s.race_date<'2026-01-01' AND s.surface='芝' AND s.distance_m=1600),0) AS turf1600_wins_3y,
 COALESCE(SUM(s.top3) FILTER (WHERE s.race_date<'2026-01-01' AND s.surface='芝' AND s.distance_m=1600),0) AS turf1600_top3_3y,
 COUNT(s.race_id) FILTER (WHERE s.race_date<'2026-01-01' AND s.surface='芝' AND s.distance_m=1600 AND s.venue_code='08') AS kyoto_turf1600_starts_3y,
 COALESCE(SUM(s.top3) FILTER (WHERE s.race_date<'2026-01-01' AND s.surface='芝' AND s.distance_m=1600 AND s.venue_code='08'),0) AS kyoto_turf1600_top3_3y,
 COUNT(s.race_id) FILTER (WHERE s.race_date>='2026-01-01') AS starts_2026_archived_partial,
 COALESCE(SUM(s.wins) FILTER (WHERE s.race_date>='2026-01-01'),0) AS wins_2026_archived_partial,
 COALESCE(SUM(s.top3) FILTER (WHERE s.race_date>='2026-01-01'),0) AS top3_2026_archived_partial,
 MAX(s.race_date) AS last_archived_jra_start_date,
 'CUTOFF_2026-11-16__2026_ARCHIVE_IS_PARTIAL' AS coverage
FROM registered_id e LEFT JOIN registered_observed_starts s ON e.candidate_order=s.candidate_order
GROUP BY e.candidate_order ORDER BY e.candidate_order;

.once reports/milecs_20261122/registered_21_turf_conditions.csv
SELECT e.candidate_order,e.horse_name,e.official_horse_id,
 s.going,COUNT(*) AS turf_starts_2023_2025, SUM(s.wins) AS turf_wins, SUM(s.top3) AS turf_top3,
 ROUND(100.0*SUM(s.top3)/COUNT(*),2) AS historical_top3_rate_pct
FROM registered_id e JOIN registered_observed_starts s ON e.candidate_order=s.candidate_order
WHERE s.surface='芝' AND s.race_date<'2026-01-01' AND s.race_id IS NOT NULL
GROUP BY e.candidate_order,s.going ORDER BY e.candidate_order,s.going;

.once reports/milecs_20261122/registered_21_recent5_from_archive.csv
WITH ranked AS (
 SELECT e.candidate_order,e.horse_name,s.race_date,s.race_id,s.venue_code,s.surface,s.going,
 s.distance_m,s.placing,s.jockey_name,s.jockey_id,
 ROW_NUMBER() OVER(PARTITION BY e.candidate_order ORDER BY s.race_date DESC,s.race_id DESC) rn
 FROM registered_id e JOIN registered_observed_starts s ON s.candidate_order=e.candidate_order
 WHERE s.race_id IS NOT NULL
)
SELECT * FROM ranked WHERE rn<=5 ORDER BY candidate_order,rn;

.once reports/milecs_20261122/provisional_jockey_lookup_candidates.csv
WITH aliases(candidate_order,alias) AS (
 VALUES (1,'ルメール'),(2,'モレイラ'),(3,'デム'),(4,'武'),(5,'松山'),(6,'西村'),(7,'バルザ'),(8,'プーシャン')
)
SELECT a.candidate_order,a.alias,s.jockey_name,s.jockey_id,COUNT(*) observed_rides_2023_2025,
 SUM(s.wins) wins_3y,SUM(s.top3) top3_3y,
 SUM(CASE WHEN s.surface='芝' AND s.distance_m=1600 THEN 1 ELSE 0 END) turf1600_rides_3y,
 SUM(CASE WHEN s.surface='芝' AND s.distance_m=1600 THEN s.top3 ELSE 0 END) turf1600_top3_3y
FROM aliases a JOIN v_archive_observed_starts s
  ON REPLACE(s.jockey_name,' ','') LIKE '%'||a.alias||'%'
WHERE s.race_date<'2026-01-01' AND s.jockey_id LIKE 'jra-jockey:pw04kmk%'
GROUP BY a.candidate_order,a.alias,s.jockey_name,s.jockey_id
ORDER BY a.candidate_order,observed_rides_2023_2025 DESC;

.once reports/milecs_20261122/registered_21_horse_id_ambiguities.csv
SELECT horse_name, COUNT(DISTINCT horse_id) id_count,GROUP_CONCAT(DISTINCT horse_id) ids
FROM archive_runners WHERE horse_name IN (SELECT horse_name FROM registered)
GROUP BY horse_name HAVING COUNT(DISTINCT horse_id)>1;


-- Provisional rider identity is backed by a unique official profile ID found
-- in the verified JRA archive, or NULL if not found (Moreira, Barzalona, etc).
-- These are screenshot rider expectations, not the published final declarations.
CREATE TEMP TABLE provisional_ride (
 candidate_order INTEGER PRIMARY KEY,
 official_jockey_id TEXT
);
INSERT INTO provisional_ride VALUES
(1,'jra-jockey:pw04kmk005339'), -- C.ルメール
(2,NULL),                      -- モレイラ has no verified ID in this historical extraction
(3,'jra-jockey:pw04kmk005473'), -- C.デムーロ, NOT M.デムーロ
(4,'jra-jockey:pw04kmk000666'), -- 武 豊, NOT 横山武史
(5,'jra-jockey:pw04kmk001126'), -- 松山 弘平
(6,'jra-jockey:pw04kmk001171'), -- 西村 淳也
(7,NULL),                      -- バルザローナ foreign archive gap
(8,'jra-jockey:pw04kmk005678'); -- A.プーシャン

.once reports/milecs_20261122/provisional_horse_jockey_pair_stats.csv
SELECT e.candidate_order,e.horse_name,e.screenshot_provisional_jockey,
 j.official_jockey_id,
 CASE WHEN j.official_jockey_id IS NULL THEN 'JOCKEY_OFFICIAL_ID_UNAVAILABLE'
      WHEN e.official_horse_id IS NULL THEN 'HORSE_OFFICIAL_ID_UNAVAILABLE'
      ELSE 'PROVISIONAL_PAIR_ID_MATCHED' END AS pair_status,
 COUNT(s.race_id) FILTER (WHERE s.race_date<'2026-01-01') AS paired_starts_2023_2025,
 COALESCE(SUM(s.wins) FILTER (WHERE s.race_date<'2026-01-01'),0) AS paired_wins_2023_2025,
 COALESCE(SUM(s.top3) FILTER (WHERE s.race_date<'2026-01-01'),0) AS paired_top3_2023_2025,
 COUNT(s.race_id) FILTER (WHERE s.race_date>='2026-01-01') AS paired_starts_2026_archived_partial,
 COALESCE(SUM(s.wins) FILTER (WHERE s.race_date>='2026-01-01'),0) AS paired_wins_2026_archived_partial,
 COALESCE(SUM(s.top3) FILTER (WHERE s.race_date>='2026-01-01'),0) AS paired_top3_2026_archived_partial
FROM registered_id e LEFT JOIN provisional_ride j ON j.candidate_order=e.candidate_order
LEFT JOIN v_archive_observed_starts s ON s.horse_id=e.official_horse_id AND s.jockey_id=j.official_jockey_id
WHERE e.candidate_order BETWEEN 1 AND 8
GROUP BY e.candidate_order ORDER BY e.candidate_order;

.once reports/milecs_20261122/registered_21_combined_2023_2026_partial_turf1600.csv
SELECT e.candidate_order,e.horse_name,e.official_horse_id,
 COUNT(s.race_id) AS observed_all_flat_starts,
 SUM(s.wins) AS observed_all_flat_wins,
 SUM(s.top3) AS observed_all_flat_top3,
 COUNT(s.race_id) FILTER (WHERE s.surface='芝' AND s.distance_m=1600) AS observed_turf1600_starts,
 COALESCE(SUM(s.wins) FILTER (WHERE s.surface='芝' AND s.distance_m=1600),0) AS observed_turf1600_wins,
 COALESCE(SUM(s.top3) FILTER (WHERE s.surface='芝' AND s.distance_m=1600),0) AS observed_turf1600_top3,
 COUNT(s.race_id) FILTER (WHERE s.surface='芝' AND s.distance_m=1600 AND s.venue_code='08') AS observed_kyoto_turf1600_starts,
 COALESCE(SUM(s.wins) FILTER (WHERE s.surface='芝' AND s.distance_m=1600 AND s.venue_code='08'),0) AS observed_kyoto_turf1600_wins,
 COALESCE(SUM(s.top3) FILTER (WHERE s.surface='芝' AND s.distance_m=1600 AND s.venue_code='08'),0) AS observed_kyoto_turf1600_top3,
 COUNT(s.race_id) FILTER (WHERE s.surface='芝' AND s.distance_m=1600 AND s.going='良') AS observed_turf1600_good_starts,
 COALESCE(SUM(s.top3) FILTER (WHERE s.surface='芝' AND s.distance_m=1600 AND s.going='良'),0) AS observed_turf1600_good_top3,
 CASE WHEN COUNT(s.race_id) FILTER (WHERE s.surface='芝' AND s.distance_m=1600)>0
      THEN ROUND(100.0*SUM(s.top3) FILTER (WHERE s.surface='芝' AND s.distance_m=1600)
           /COUNT(s.race_id) FILTER (WHERE s.surface='芝' AND s.distance_m=1600),1) END AS raw_historical_turf1600_top3_pct,
 'NOT_FORECAST_PROBABILITY__2026_INCOMPLETE' AS caveat
FROM registered_id e
LEFT JOIN registered_observed_starts s ON e.candidate_order=s.candidate_order
GROUP BY e.candidate_order ORDER BY e.candidate_order;
