"""Merge verified JRA postrace full-runner SQLite into five-source companion v2.

Never overwrite canonical Library v11 or existing verified companion v1.
Original external preoff feature table stays untouched (0 rows). The 495
new rows represent JRA OFFICIAL RESULT HISTORY, not preoff predictors for
2026-11-08 and not proof of horse IDs.
"""
import hashlib,json,sqlite3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/"operations/data_updates/multisource_overlay_20261108.sqlite"
OLD_MAN=ROOT/"operations/data_updates/multisource_overlay_20261108_audit.json"
NEW=ROOT/"operations/data_updates/jra_official_full_runner_history_20261108_v2.sqlite"
NEW_MAN=ROOT/"operations/data_updates/jra_official_full_runner_history_20261108_v2_audit.json"
OUT=ROOT/"operations/data_updates/multisource_overlay_20261108_v2.sqlite"
AUDIT=ROOT/"operations/data_updates/multisource_overlay_20261108_v2_audit.json"
MD=ROOT/"reports/v51/MULTISOURCE_OFFICIAL_HISTORY_V2_REALDATA.md"
def checksum(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def verify(path,meta,name):
    d=json.loads(meta.read_text())
    key="overlay_sha256" if name=="old" else "sqlite_sha256"
    size="overlay_size_bytes" if name=="old" else "sqlite_size_bytes"
    if checksum(path)!=d[key] or path.stat().st_size!=d[size]:
        raise ValueError("source binary hash mismatch "+name)
    with sqlite3.connect(f"file:{path.resolve()}?mode=ro",uri=True) as c:
        if c.execute("PRAGMA integrity_check").fetchone()[0]!="ok" or c.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("source sqlite integrity "+name)
    return d
def main():
    if OUT.exists():raise FileExistsError("v2 supplement must never overwrite")
    old=verify(OLD,OLD_MAN,"old")
    official=verify(NEW,NEW_MAN,"new")
    if official["counts"]["races"]!=36 or official["counts"]["runners"]!=495:
        raise ValueError("official source not all 495 JRA result rows")
    src=sqlite3.connect(f"file:{OLD.resolve()}?mode=ro",uri=True)
    target=sqlite3.connect(OUT)
    try:src.backup(target)
    finally:src.close()
    try:
        target.execute("PRAGMA foreign_keys=ON")
        target.executescript("""
        CREATE TABLE jra_result_history_full(
          race_id TEXT NOT NULL,horse_number INTEGER NOT NULL,horse_name TEXT NOT NULL,
          official_horse_id TEXT,official_horse_id_is_confirmed INTEGER NOT NULL DEFAULT 0,
          finishing_position INTEGER NOT NULL,final_popularity INTEGER NOT NULL,
          sex_age TEXT,carried_weight REAL,jockey_name TEXT,
          time_seconds REAL,margin TEXT,corner_positions_json TEXT,
          final3_seconds REAL,bodyweight_kg INTEGER,bodyweight_delta_kg INTEGER,
          trainer_name TEXT,source_result_url TEXT NOT NULL,
          source_sha256 TEXT NOT NULL,source_observed_at TEXT NOT NULL,
          result_only_not_preoff INTEGER NOT NULL CHECK(result_only_not_preoff=1),
          PRIMARY KEY(race_id,horse_number),
          FOREIGN KEY(race_id) REFERENCES jra_official_race_checkpoint(race_id_text));
        CREATE INDEX jra_history_by_name ON jra_result_history_full(horse_name);
        CREATE INDEX jra_history_by_rider ON jra_result_history_full(jockey_name);
        """)
        source=sqlite3.connect(f"file:{NEW.resolve()}?mode=ro",uri=True)
        try:
            official_races={r[0]:r for r in source.execute(
                "SELECT race_id,official_url,sha256,observed_at FROM source_race")}
            checkpoint={r[0]:r for r in target.execute(
                "SELECT race_id_text, result_headcount, podium_numbers_json FROM jra_official_race_checkpoint")}
            if set(official_races)!=set(checkpoint):
                raise ValueError("source/overlay JRA official 36 race keys mismatch")
            for race,headcount,podium_json in checkpoint.values():
                ns=[r[0] for r in source.execute(
                    "SELECT horse_number FROM source_runner WHERE race_id=? ORDER BY finish",(race,))]
                if len(ns)!=headcount or ns[:3]!=json.loads(podium_json):
                    raise ValueError("JRA full runner race count/podium mismatch: "+race)
            sql="""SELECT race_id,horse_number,horse_name,official_horse_id,
               finish,popularity_final,sex_age,carried_weight,jockey,time_seconds,
               margin,corner_positions_json,last3_seconds,bodyweight_kg,
               bodyweight_delta_kg,trainer FROM source_runner"""
            for row in source.execute(sql):
                race=row[0]
                url,digest,seen=official_races[race][1:]
                target.execute(
                    "INSERT INTO jra_result_history_full VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)",
                    (row[0],row[1],row[2],row[3],int(row[3] is not None),
                     *row[4:],url,digest,seen))
        finally:source.close()
        target.execute("INSERT OR REPLACE INTO overlay_manifest VALUES(?,?)",
                       ("source_official_fullrunner_v2_sha256",official["sqlite_sha256"]))
        target.execute("INSERT OR REPLACE INTO overlay_manifest VALUES(?,?)",
                       ("jra_official_postrace_runner_rows","495"))
        target.execute("INSERT OR REPLACE INTO overlay_manifest VALUES(?,?)",
                       ("new_external_preoff_horse_features","0"))
        target.commit()
        n=target.execute("SELECT count(*) FROM jra_result_history_full").fetchone()[0]
        t=target.execute("SELECT count(*) FROM multi_source_observation").fetchone()[0]
        if n!=495 or t!=0:raise ValueError("new+old observation count invalid")
        if target.execute("PRAGMA integrity_check").fetchone()[0]!="ok" or target.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("merged SQLite integrity failed")
    finally:target.close()
    result={"schema":"jra-multisource-companion-v2-actual-history",
            "sha256":checksum(OUT),"size_bytes":OUT.stat().st_size,
            "sqlite_integrity":"ok","parent_overlay_sha256":old["overlay_sha256"],
            "official_fullrunner_sha256":official["sqlite_sha256"],
            "jra_official_races":36,"jra_official_full_runner_rows":495,
            "final_time_rows":official["counts"]["times"],
            "final3_rows":official["counts"]["last3"],
            "jockey_rows":official["counts"]["jockeys"],
            "official_horse_ids_verified":official["counts"]["horse_ids"],
            "new_external_preoff_features":0,"train_for_same_race":False,
            "production_v50_unchanged":True,
            "canonical_library_v11_not_overwritten":True}
    AUDIT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    MD.parent.mkdir(parents=True,exist_ok=True)
    MD.write_text("# 公式JRA全頭成績をマルチソース補助DBに統合\n\n"
       "2026年11月8日JRA結果36R、全495頭の実成績を補助DB v2へ統合。\n\n"
       f"- 走破タイム495、上がり495、騎手494、公式ID0。\n"
       "- 馬番/馬名/人気/着順/斤量/馬体重/走破タイム/推定上がり/騎手等を後日履歴として保持。\n"
       "- 同日・同レースの発走前特徴量として使うことは禁止。\n"
       "- 既存5ソースの新規馬別の事前特徴量は0。V50/V51の改善効果は未検証。\n"
       "- 正本Library v11は上書きしていない。完全ハッシュ検証ができるまでは安全な補助DBとして分離。\n"
       f"- 保存DB SHA256: {result['sha256']}。\n")
    print(json.dumps(result,ensure_ascii=False))
if __name__=="__main__":main()
