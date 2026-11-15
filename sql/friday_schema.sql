PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS source_manifest(
 source_sha256 TEXT PRIMARY KEY CHECK(length(source_sha256)=64),
 source_url TEXT NOT NULL,
 captured_at_jst TEXT NOT NULL,
 source_kind TEXT NOT NULL CHECK(source_kind IN ('official_result','official_card')),
 verification_status TEXT NOT NULL CHECK(verification_status='verified')
);
CREATE TABLE IF NOT EXISTS races(
 race_id TEXT PRIMARY KEY,
 race_date TEXT NOT NULL,
 venue TEXT NOT NULL,
 race_number INTEGER NOT NULL CHECK(race_number BETWEEN 1 AND 12),
 surface TEXT NOT NULL CHECK(surface IN ('芝','ダート')),
 going TEXT NOT NULL CHECK(going IN ('良','稍重','重','不良')),
 distance_m INTEGER NOT NULL CHECK(distance_m > 0),
 source_sha256 TEXT NOT NULL REFERENCES source_manifest(source_sha256)
);
CREATE TABLE IF NOT EXISTS historical_starts(
 race_id TEXT NOT NULL REFERENCES races(race_id),
 horse_id TEXT NOT NULL CHECK(length(horse_id)>0),
 horse_name TEXT NOT NULL,
 horse_number INTEGER NOT NULL CHECK(horse_number>0),
 jockey_id TEXT NOT NULL CHECK(length(jockey_id)>0),
 jockey_name TEXT NOT NULL,
 finish_position INTEGER CHECK(finish_position>0),
 started INTEGER NOT NULL CHECK(started IN (0,1)),
 PRIMARY KEY(race_id,horse_id),
 UNIQUE(race_id,horse_number),
 CHECK(started=1 OR finish_position IS NULL)
);
CREATE TABLE IF NOT EXISTS declared_entries(
 target_race_id TEXT NOT NULL,
 target_date TEXT NOT NULL,
 venue TEXT NOT NULL,
 race_number INTEGER NOT NULL CHECK(race_number BETWEEN 1 AND 12),
 horse_number INTEGER NOT NULL CHECK(horse_number>0),
 horse_id TEXT NOT NULL,
 horse_name TEXT NOT NULL,
 jockey_id TEXT NOT NULL,
 jockey_name TEXT NOT NULL,
 source_sha256 TEXT NOT NULL REFERENCES source_manifest(source_sha256),
 PRIMARY KEY(target_race_id,horse_number)
);
CREATE INDEX IF NOT EXISTS ix_starts_horse ON historical_starts(horse_id);
CREATE INDEX IF NOT EXISTS ix_starts_jockey ON historical_starts(jockey_id);
CREATE INDEX IF NOT EXISTS ix_races_conditions ON races(race_date,surface,going,venue,distance_m);
CREATE VIEW IF NOT EXISTS v_eligible_history AS
 SELECT s.horse_id,s.jockey_id,s.race_id,r.race_date,r.venue,r.surface,r.going,r.distance_m,
        s.finish_position,CASE WHEN s.finish_position=1 THEN 1 ELSE 0 END AS win,
        CASE WHEN s.finish_position BETWEEN 1 AND 3 THEN 1 ELSE 0 END AS top3
 FROM historical_starts s JOIN races r ON r.race_id=s.race_id
 WHERE s.started=1 AND s.finish_position IS NOT NULL;
