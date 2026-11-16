-- Fallback-friendly race-specific historical statistics for *available* card rows.
-- Card staging is secondary/unverified unless separately source-audited.
-- Historical count window is 2023-01-01 through 2025-12-31, excluding 2026 partial archive.
.bail on
CREATE TEMP TABLE staged_cards (
  date TEXT,venue TEXT,race_no TEXT,race_name TEXT,surface TEXT,distance_m TEXT,
  horse_no TEXT,horse_name TEXT,jockey_name TEXT,card_status TEXT,
  source_type TEXT,source_url TEXT,source_captured_utc TEXT
);
.mode csv
.import --skip 1 reports/friday_operational/cards_staging.csv temp.staged_cards

CREATE TEMP TABLE historical_flat AS
SELECT * FROM v_archive_observed_starts WHERE race_date >= '2023-01-01' AND race_date < '2026-01-01';
CREATE INDEX idx_hist_horse ON historical_flat(horse_id);
CREATE INDEX idx_hist_jockey ON historical_flat(jockey_id);

-- Historical IDs are allowed only on an exact and unambiguous name match.
CREATE TEMP TABLE known_horses AS
SELECT DISTINCT horse_name,horse_id FROM archive_runners;
CREATE INDEX idx_known_horse_name ON known_horses(horse_name);
CREATE TEMP TABLE known_jockeys AS
SELECT DISTINCT jockey_name,jockey_id FROM archive_runners
WHERE jockey_id LIKE 'jra-jockey:pw04kmk%';
CREATE INDEX idx_known_jockey_name ON known_jockeys(jockey_name);

CREATE TEMP TABLE horse_identity AS
SELECT s.horse_name,COUNT(DISTINCT k.horse_id) id_candidates,
 CASE WHEN COUNT(DISTINCT k.horse_id)=1 THEN MIN(k.horse_id) END horse_id
FROM (SELECT DISTINCT horse_name FROM staged_cards) s
LEFT JOIN known_horses k USING(horse_name) GROUP BY s.horse_name;
CREATE TEMP TABLE jockey_identity AS
SELECT s.jockey_name,COUNT(DISTINCT k.jockey_id) id_candidates,
 CASE WHEN COUNT(DISTINCT k.jockey_id)=1 THEN MIN(k.jockey_id) END jockey_id
FROM (SELECT DISTINCT jockey_name FROM staged_cards WHERE jockey_name!='') s
LEFT JOIN known_jockeys k USING(jockey_name) GROUP BY s.jockey_name;

CREATE TEMP TABLE horse_totals AS
SELECT horse_id,COUNT(*) starts,SUM(wins) wins,SUM(top3) top3
FROM historical_flat GROUP BY horse_id;
CREATE INDEX idx_horse_totals ON horse_totals(horse_id);
CREATE TEMP TABLE jockey_totals AS
SELECT jockey_id,COUNT(*) starts,SUM(wins) wins,SUM(top3) top3
FROM historical_flat WHERE jockey_id LIKE 'jra-jockey:pw04kmk%'
GROUP BY jockey_id;
CREATE INDEX idx_jockey_totals ON jockey_totals(jockey_id);
CREATE TEMP TABLE pair_totals AS
SELECT horse_id,jockey_id,COUNT(*) starts,SUM(wins) wins,SUM(top3) top3
FROM historical_flat WHERE jockey_id LIKE 'jra-jockey:pw04kmk%'
GROUP BY horse_id,jockey_id;
CREATE INDEX idx_pair_totals ON pair_totals(horse_id,jockey_id);
CREATE TEMP TABLE course_totals AS
SELECT horse_id,venue_code,surface,distance_m,COUNT(*) starts,SUM(wins) wins,SUM(top3) top3
FROM historical_flat GROUP BY horse_id,venue_code,surface,distance_m;
CREATE INDEX idx_course_totals ON course_totals(horse_id,venue_code,surface,distance_m);

CREATE TEMP VIEW joined_cards AS
SELECT c.*,
CASE c.venue
 WHEN '札幌' THEN '01' WHEN '函館' THEN '02' WHEN '福島' THEN '03'
 WHEN '新潟' THEN '04' WHEN '東京' THEN '05' WHEN '中山' THEN '06'
 WHEN '中京' THEN '07' WHEN '京都' THEN '08' WHEN '阪神' THEN '09' WHEN '小倉' THEN '10'
 END AS venue_code,
 h.horse_id, h.id_candidates AS horse_id_candidates,
 j.jockey_id,COALESCE(j.id_candidates,0) AS jockey_id_candidates
FROM staged_cards c
LEFT JOIN horse_identity h USING(horse_name)
LEFT JOIN jockey_identity j USING(jockey_name);

.headers on
.mode csv
.once reports/friday_operational/cards_joined.csv
SELECT c.date,c.venue,c.race_no,c.race_name,c.surface,c.distance_m,
 c.horse_no,c.horse_name,c.jockey_name,c.card_status,c.source_type,c.source_url,c.source_captured_utc,
 COALESCE(c.horse_id,'') horse_id,COALESCE(c.jockey_id,'') jockey_id,
 CASE WHEN c.horse_id_candidates=1 THEN 'MATCHED_EXACT_UNIQUE_NAME'
      WHEN c.horse_id_candidates=0 THEN 'NO_HORSE_ID_HISTORY'
      ELSE 'AMBIGUOUS_HORSE_NAME' END horse_id_status,
 CASE WHEN c.jockey_name='' THEN 'JOCKEY_NOT_LISTED'
      WHEN c.jockey_id_candidates=1 THEN 'MATCHED_EXACT_UNIQUE_NAME'
      WHEN c.jockey_id_candidates=0 THEN 'NO_JOCKEY_ID_HISTORY'
      ELSE 'AMBIGUOUS_JOCKEY_NAME' END jockey_id_status,
 CASE WHEN c.horse_id IS NOT NULL THEN CAST(COALESCE(ht.starts,0) AS TEXT) ELSE '' END horse_starts,
 CASE WHEN c.horse_id IS NOT NULL THEN CAST(COALESCE(ht.wins,0) AS TEXT) ELSE '' END horse_wins,
 CASE WHEN c.horse_id IS NOT NULL THEN CAST(COALESCE(ht.top3,0) AS TEXT) ELSE '' END horse_top3,
 CASE WHEN c.jockey_id IS NOT NULL THEN CAST(COALESCE(jt.starts,0) AS TEXT) ELSE '' END jockey_starts,
 CASE WHEN c.jockey_id IS NOT NULL THEN CAST(COALESCE(jt.wins,0) AS TEXT) ELSE '' END jockey_wins,
 CASE WHEN c.jockey_id IS NOT NULL THEN CAST(COALESCE(jt.top3,0) AS TEXT) ELSE '' END jockey_top3,
 CASE WHEN c.horse_id IS NOT NULL AND c.jockey_id IS NOT NULL THEN CAST(COALESCE(pt.starts,0) AS TEXT) ELSE '' END pair_starts,
 CASE WHEN c.horse_id IS NOT NULL AND c.jockey_id IS NOT NULL THEN CAST(COALESCE(pt.wins,0) AS TEXT) ELSE '' END pair_wins,
 CASE WHEN c.horse_id IS NOT NULL AND c.jockey_id IS NOT NULL THEN CAST(COALESCE(pt.top3,0) AS TEXT) ELSE '' END pair_top3,
 CASE WHEN c.horse_id IS NOT NULL AND c.venue_code IS NOT NULL AND c.surface IN ('芝','ダート')
           AND c.distance_m GLOB '[0-9]*' AND c.distance_m!=''
      THEN CAST(COALESCE(ct.starts,0) AS TEXT) ELSE '' END condition_starts,
 CASE WHEN c.horse_id IS NOT NULL AND c.venue_code IS NOT NULL AND c.surface IN ('芝','ダート')
           AND c.distance_m GLOB '[0-9]*' AND c.distance_m!=''
      THEN CAST(COALESCE(ct.top3,0) AS TEXT) ELSE '' END condition_top3
FROM joined_cards c
LEFT JOIN horse_totals ht ON ht.horse_id=c.horse_id
LEFT JOIN jockey_totals jt ON jt.jockey_id=c.jockey_id
LEFT JOIN pair_totals pt ON pt.horse_id=c.horse_id AND pt.jockey_id=c.jockey_id
LEFT JOIN course_totals ct ON ct.horse_id=c.horse_id AND ct.venue_code=c.venue_code
 AND ct.surface=c.surface AND ct.distance_m=CAST(c.distance_m AS INTEGER)
ORDER BY c.date,c.venue,c.race_no,
 CASE WHEN c.horse_no GLOB '[0-9]*' AND c.horse_no!='' THEN CAST(c.horse_no AS INTEGER) ELSE 100 END,
 c.horse_name;

.once reports/friday_operational/card_coverage.csv
SELECT date,venue,race_no,race_name,source_type,card_status,COUNT(*) AS horses_found,
 SUM(CASE WHEN horse_id_candidates=1 THEN 1 ELSE 0 END) AS horse_ids_matched_by_name,
 SUM(CASE WHEN jockey_id_candidates=1 THEN 1 ELSE 0 END) AS jockey_ids_matched_by_name,
 'PARTIAL_SOURCE_ROSTER_NOT_OFFICIAL_CERTIFIED' AS roster_status
FROM joined_cards
GROUP BY date,venue,race_no,race_name,source_type,card_status
ORDER BY date,venue,CAST(race_no AS INTEGER);

.once reports/friday_operational/unmatched_card_entries.csv
SELECT date,venue,race_no,horse_no,horse_name,jockey_name,
 COALESCE(horse_id_candidates,0) horse_id_candidates,
 jockey_id_candidates,source_type,source_url
FROM joined_cards
WHERE horse_id_candidates!=1 OR jockey_id_candidates!=1
ORDER BY date,venue,race_no,horse_no;
