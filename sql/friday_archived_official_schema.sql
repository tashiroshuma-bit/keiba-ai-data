PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS archive_races(
 race_id TEXT PRIMARY KEY,
 race_date TEXT NOT NULL,
 year INTEGER NOT NULL,
 venue_code TEXT NOT NULL,
 meeting INTEGER NOT NULL,
 meeting_day INTEGER NOT NULL,
 race_number INTEGER NOT NULL,
 source_url TEXT NOT NULL,
 source_sha256 TEXT NOT NULL CHECK(length(source_sha256)=64),
 observed_at TEXT NOT NULL,
 horse_count INTEGER NOT NULL,
 source_scope TEXT NOT NULL,
 surface TEXT NOT NULL,
 going TEXT NOT NULL,
 distance_m INTEGER NOT NULL,
 metadata_verified INTEGER NOT NULL CHECK(metadata_verified IN (0,1))
);
CREATE TABLE IF NOT EXISTS archive_runners(
 race_id TEXT NOT NULL REFERENCES archive_races(race_id),
 horse_number INTEGER NOT NULL,
 horse_name TEXT NOT NULL,
 horse_id TEXT NOT NULL CHECK(horse_id LIKE 'jra:%'),
 finish_position TEXT,
 result_status TEXT,
 jockey_name TEXT NOT NULL,
 jockey_link TEXT,
 source_sha256 TEXT NOT NULL,
 jockey_id TEXT NOT NULL DEFAULT '',
 PRIMARY KEY(race_id,horse_number)
);
CREATE INDEX IF NOT EXISTS ix_archive_horse ON archive_runners(horse_id);
CREATE INDEX IF NOT EXISTS ix_archive_jockey ON archive_runners(jockey_id);
CREATE INDEX IF NOT EXISTS ix_archive_conditions ON archive_races(race_date,surface,going,distance_m);
CREATE INDEX IF NOT EXISTS ix_archive_date ON archive_races(race_date);
CREATE VIEW IF NOT EXISTS v_archive_observed_starts AS
 SELECT r.race_id,r.race_date,r.venue_code,r.race_number,
 s.horse_id,s.horse_name,s.jockey_name,s.jockey_id,s.jockey_link,s.horse_number,
 r.surface,r.going,r.distance_m,
 CAST(s.finish_position AS INTEGER) AS placing,
 CASE WHEN CAST(s.finish_position AS INTEGER)=1 THEN 1 ELSE 0 END AS wins,
 CASE WHEN CAST(s.finish_position AS INTEGER) BETWEEN 1 AND 3 THEN 1 ELSE 0 END AS top3
 FROM archive_runners s JOIN archive_races r ON r.race_id=s.race_id
 WHERE r.metadata_verified=1 AND r.surface IN ('芝','ダート') AND s.finish_position IS NOT NULL AND s.finish_position!=''
 AND s.finish_position NOT GLOB '*[^0-9]*' AND CAST(s.finish_position AS INTEGER)>0;

-- Officially cancelled scheduled race panels contain zero actual starters.
-- Keep separately from official results; never count scheduled runners as starts.
CREATE TABLE IF NOT EXISTS archive_cancelled_scheduled_races (
 race_id TEXT PRIMARY KEY,
 year INTEGER NOT NULL,
 race_date TEXT NOT NULL,
 venue_code TEXT NOT NULL,
 race_number INTEGER NOT NULL CHECK(race_number BETWEEN 1 AND 12),
 race_status TEXT NOT NULL CHECK(race_status='CANCELLED_NO_OFFICIAL_RESULT'),
 reason TEXT NOT NULL,
 official_evidence_url TEXT NOT NULL CHECK(official_evidence_url LIKE 'https://www.jra.go.jp/%'),
 evidence_status TEXT NOT NULL CHECK(evidence_status='JRA_OFFICIAL_URL_VERIFIED_NOT_ORIGINAL_BYTE_SHA'),
 actual_starters INTEGER NOT NULL DEFAULT 0 CHECK(actual_starters=0)
);
