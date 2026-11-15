-- Separate real-data research seed tables. Not a promotion to a full JRA official-history DB.
CREATE TABLE IF NOT EXISTS tracked_source_db (
  db_sha256 TEXT PRIMARY KEY CHECK(length(db_sha256)=64),
  relative_path TEXT NOT NULL,
  provenance TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status='DERIVED_NOT_ORIGINAL')
);
CREATE TABLE IF NOT EXISTS tracked_result_runner (
  race_date TEXT NOT NULL,
  source_race_key TEXT NOT NULL,
  venue TEXT NOT NULL,
  race_number INTEGER NOT NULL,
  horse_number INTEGER NOT NULL,
  horse_id TEXT NOT NULL,
  horse_name TEXT NOT NULL,
  jockey_name TEXT NOT NULL,
  finish_position INTEGER,
  source_url TEXT NOT NULL,
  source_html_sha256 TEXT NOT NULL CHECK(length(source_html_sha256)=64),
  source_db_sha256 TEXT NOT NULL REFERENCES tracked_source_db(db_sha256),
  PRIMARY KEY(race_date,source_race_key,horse_number)
);
CREATE INDEX IF NOT EXISTS idx_tracked_result_horse ON tracked_result_runner(horse_id);
CREATE TABLE IF NOT EXISTS tracked_profile_past_run (
  horse_id TEXT NOT NULL,
  horse_name TEXT NOT NULL,
  prior_race_date TEXT NOT NULL,
  venue TEXT NOT NULL,
  race_name TEXT NOT NULL,
  distance_surface TEXT NOT NULL,
  going TEXT,
  finish_position INTEGER,
  jockey_name TEXT,
  source_profile_sha256 TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  source_db_sha256 TEXT NOT NULL REFERENCES tracked_source_db(db_sha256),
  PRIMARY KEY(horse_id,prior_race_date,venue,race_name)
);
CREATE INDEX IF NOT EXISTS idx_tracked_past_conditions ON tracked_profile_past_run(horse_id,distance_surface,going);
