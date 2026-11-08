"""Build a source-backed per-horse historical form feature bank for FUTURE V51.

Joins the Nov8 JRA exact 497 horse ID proofs to bounded 2026-11-08
profile captures (Kyoto12 and Tokyo11/12). No future race observations,
no name-only IDs, no 2026-11-08 retrospective forecast replays.

Source availability is proven no later than the actual profile capture time.
Historical first-publication timestamp remains UNKNOWN: never invent it.
"""
from __future__ import annotations
import datetime as dt,hashlib,json,re,sqlite3
from pathlib import Path
from collections import defaultdict

ROOT=Path(__file__).resolve().parents[1]
ROSTER=ROOT/"operations/data_updates/jra_official_20261108_all_runner_history_v2.sqlite"
SOURCES=[
 ROOT/"operations/data_updates/jra_official_20261108_kyoto12_horse_profiles_v1.sqlite",
 ROOT/"operations/data_updates/jra_official_20261108_tokyo11_12_profiles_v1.sqlite"]
OUTPUT=ROOT/"operations/data_updates/jra_v51_future_horse_form_bank_20261108.sqlite"
AUDIT=ROOT/"operations/data_updates/jra_v51_future_horse_form_bank_20261108_audit.json"
REPORT=ROOT/"reports/v51/JRA_VERIFIED_FUTURE_HORSE_FORM_BANK_20261108.md"

def source_sha(p):
    h=hashlib.sha256()
    with Path(p).open("rb") as s:
        for chunk in iter(lambda:s.read(1024*1024),b""):h.update(chunk)
    return h.hexdigest()
def parse_time(s):
    t=dt.datetime.fromisoformat(str(s).replace("Z","+00:00"))
    if t.tzinfo is None:raise ValueError("missing timezone")
    return t
def build(out=OUTPUT):
    if out.exists():raise FileExistsError("do not overwrite previous feature bank")
    if not all(s.exists() for s in SOURCES):raise FileNotFoundError("prior profile batch missing")
    with sqlite3.connect(f"file:{ROSTER}?mode=ro",uri=True) as co:
        raw=co.execute("SELECT race,horse_id,horse_name FROM runner_postrace").fetchall()
        full={(h,n) for race,h,n in raw}
        roster={h:(race,n) for race,h,n in raw}
        if len(full)<450:raise ValueError("official full JRA ID roster incomplete")
    items=[]
    for file in SOURCES:
        with sqlite3.connect(f"file:{file}?mode=ro",uri=True) as co:
            if co.execute("PRAGMA integrity_check").fetchone()[0]!="ok":raise ValueError("source corrupt")
            profiles=co.execute("SELECT horse_id,horse_name,profile_url,source_sha256,observed_at,past_runs FROM official_profile").fetchall()
            for hid,name,url,sha,seen,count in profiles:
                if not hid.startswith("jra:") or (hid,name) not in full:
                    raise ValueError("official horse ID or name mismatched across JRA sources")
                if parse_time(seen)<dt.datetime(2026,11,8,tzinfo=dt.timezone.utc):
                    raise ValueError("historical first observation may not be inferred")
                past=co.execute("""SELECT prior_race_date,venue,race_name,distance_surface,going,
                   field_size,popularity_final,finish_position,jockey_name,assigned_weight_kg,
                   bodyweight_kg,time_text,rating_text,opponent_text,profile_observed_at,source_profile_sha256
                   FROM official_past_run WHERE horse_id=? ORDER BY prior_race_date DESC""",(hid,)).fetchall()
                if len(past)!=count:raise ValueError("past-run rows count mismatch")
                if any(x[0]>="2026-11-08" for x in past):
                    raise ValueError("cannot use Nov8 race result as preoff historical prior")
                if any(x[-2]!=seen or x[-1]!=sha for x in past):
                    raise ValueError("underlying profile provenance mismatch")
                if not url.startswith("https://www.jra.go.jp/"):
                    raise ValueError("official JRA profile link required")
                items.append({"horse_id":hid,"horse_name":name,
                    "race_of_original_link":roster[hid][0],
                    "profile_url":url,"profile_sha256":sha,
                    "first_verified_available_at":seen,
                    "historic_first_published_at":None,
                    "past":past})
    if len({x["horse_id"] for x in items})!=len(items):
        raise ValueError("duplicate profile cross-batch horse ID")
    if len(items)<40:raise ValueError("not enough complete future horse profile records")
    out.parent.mkdir(parents=True,exist_ok=True)
    con=sqlite3.connect(out)
    try:
        con.execute("""CREATE TABLE future_horse_form(
            horse_id TEXT PRIMARY KEY, horse_name TEXT NOT NULL,
            linked_nov08_race TEXT NOT NULL,
            profile_url TEXT NOT NULL, profile_sha256 TEXT NOT NULL,
            verified_available_at TEXT NOT NULL,
            historical_original_published_at TEXT,
            prior_runs INTEGER NOT NULL,
            recent3_runs INTEGER NOT NULL,
            recent3_wins INTEGER NOT NULL,
            recent3_top3 INTEGER NOT NULL,
            recent3_mean_finish REAL,
            recent3_mean_relative_finish REAL,
            recent3_turf_runs INTEGER NOT NULL,
            recent3_dirt_runs INTEGER NOT NULL,
            recent3_mean_fair_speed_ms REAL,
            first_eligible_asof TEXT NOT NULL,
            usable_for_20261108_retro_forecast INTEGER NOT NULL CHECK(usable_for_20261108_retro_forecast=0),
            evidence_timestamp_basis TEXT NOT NULL CHECK(evidence_timestamp_basis='verified_observed_no_later_than')
            )""")
        for p in items:
            past=p["past"][:3]
            finish=[v[7] for v in past if isinstance(v[7],int) and v[7]>0]
            relative=[(v[5]-v[7])/(v[5]-1) for v in past if
                  isinstance(v[5],int) and v[5]>1 and isinstance(v[7],int) and 1<=v[7]<=v[5]]
            speeds=[]
            for v in past:
                dist=re.search(r"(?:芝|ダート)(\d{3,4})",str(v[3] or ""))
                tm=re.fullmatch(r"(?:(\d+):)?(\d{1,2})\.(\d)",str(v[11] or ""))
                if dist and tm:
                    seconds=(int(tm[1] or 0)*60)+int(tm[2])+int(tm[3])*.1
                    if seconds>15:speeds.append(int(dist[1])/seconds)
            con.execute("INSERT INTO future_horse_form VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(
                p["horse_id"],p["horse_name"],p["race_of_original_link"],
                p["profile_url"],p["profile_sha256"],p["first_verified_available_at"],None,
                len(p["past"]),len(past),
                sum(v[7]==1 for v in past),sum(isinstance(v[7],int) and 1<=v[7]<=3 for v in past),
                sum(finish)/len(finish) if finish else None,
                sum(relative)/len(relative) if relative else None,
                sum(str(v[3]).startswith("芝") for v in past),
                sum(str(v[3]).startswith("ダート") for v in past),
                sum(speeds)/len(speeds) if speeds else None,
                p["first_verified_available_at"],0,"verified_observed_no_later_than"))
        con.commit()
        if con.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
            raise ValueError("bank integrity invalid")
        if con.execute("SELECT COUNT(*) FROM future_horse_form").fetchone()[0]!=len(items):
            raise ValueError("re-read failed")
        by_race=dict(con.execute("SELECT linked_nov08_race,count(*) FROM future_horse_form GROUP BY linked_nov08_race").fetchall())
        prior=sum(p["past"].__len__() for p in items)
        with_speed=con.execute("SELECT count(*) FROM future_horse_form WHERE recent3_mean_fair_speed_ms IS NOT NULL").fetchone()[0]
    finally:con.close()
    result={"schema":"v51-jra-observed-future-horse-form-bank-v1",
       "source_races":sorted(by_race),
       "verified_horse_ids":len(items),"prior_race_rows":prior,
       "by_linked_race":by_race,
       "recent_speed_computed_horses":with_speed,
       "data_target_date":"2026-11-08",
       "original_published_at_verified":False,
       "availability_proven_at_or_before_capture":True,
       "same_2026_11_08_forecast_eligible":False,
       "eligible_for_forecasts_after_capture_with_matching_official_id":True,
       "production_v50_v51_accuracy_uplift_not_evaluated":True,
       "no_name_only_id_join":True,
       "sqlite_size":out.stat().st_size,"sqlite_sha256":source_sha(out),
       "source_sha256":{p.name:source_sha(p) for p in SOURCES}}
    AUDIT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    l=["# V51 将来予測用 JRA公式・馬別近走特徴量バンク","",
       "JRA公式プロフィールを取得した日時より後のレース専用。2026/11/8当時の回顧的予測には使用禁止。","",
       f"公式馬ID：**{result['verified_horse_ids']}頭**。各馬の過去走：**{prior}件**。","",
       "|リンク元レース|公式ID付きの馬|","|---|---:|"]
    for k,v in by_race.items():l.append(f"|{k}|{v}|")
    l+=["","直近3走の着順・上位3着率・芝/ダート・相対着順・距離/タイムの速度参考値を保存。",
        "**速度値は距離・馬場・相手関係を未補正のため、単独で能力差と解釈しない。**",
        "過去の個々のレース結果の『初回公開時刻』は不明。今回のプロフィール観測時刻より後の予測に限り、すでに公開されていた事実として使用可能。",
        "公式馬IDの未照合対象へ馬名類似で連結しない。",
        "この特徴量だけでは、V50/V51の同一時刻に凍結された独立的中率検証はまだできない。",
        ""]
    REPORT.parent.mkdir(parents=True,exist_ok=True)
    REPORT.write_text("\n".join(l))
    print(json.dumps(result,ensure_ascii=False))
    return result
if __name__=="__main__":build()
