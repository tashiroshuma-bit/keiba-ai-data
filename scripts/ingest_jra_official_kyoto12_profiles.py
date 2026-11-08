"""Ingest limited JRA official horse past results for 18 Kyoto12 runners.

Source: exact official horse-profile URLs obtained from the full official
result table, not guessed name-to-ID links. This is a gentle 18-page
source-backed batch, not an unrestricted website scraper or vendor data.

Profile observation is POST-RACE Nov8; prior result dates are in the past
but exact historical publication dates are not established. Only future
forecasts after actual observation may consume the data.
"""
from __future__ import annotations
import datetime as dt,hashlib,json,re,sqlite3,time
from urllib.request import Request,urlopen
from pathlib import Path
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
FULL=ROOT/"operations/data_updates/jra_official_20261108_all_runner_history_v2.sqlite"
OUT=ROOT/"operations/data_updates/jra_official_20261108_kyoto12_horse_profiles_v1.sqlite"
AUDIT=ROOT/"operations/data_updates/jra_official_20261108_kyoto12_horse_profiles_v1_audit.json"

SCHEMA="""
CREATE TABLE official_profile(
 horse_id TEXT PRIMARY KEY,horse_name TEXT NOT NULL,profile_url TEXT NOT NULL,
 source_sha256 TEXT NOT NULL,observed_at TEXT NOT NULL,
 exact_historical_publication_time_verified INTEGER NOT NULL DEFAULT 0 CHECK(exact_historical_publication_time_verified=0),
 original_20261108_preoff_use INTEGER NOT NULL DEFAULT 0 CHECK(original_20261108_preoff_use=0),
 past_runs INTEGER NOT NULL
);
CREATE TABLE official_past_run(
 horse_id TEXT NOT NULL,prior_race_date TEXT NOT NULL,venue TEXT NOT NULL,
 race_name TEXT NOT NULL,distance_surface TEXT NOT NULL,going TEXT,
 field_size INTEGER,popularity_final INTEGER,finish_position INTEGER,
 jockey_name TEXT,assigned_weight_kg REAL,bodyweight_kg INTEGER,
 time_text TEXT,rating_text TEXT,opponent_text TEXT,
 profile_observed_at TEXT NOT NULL,source_profile_sha256 TEXT NOT NULL,
 original_publication_at TEXT,
 PRIMARY KEY(horse_id,prior_race_date,venue,race_name),
 FOREIGN KEY(horse_id) REFERENCES official_profile(horse_id)
);
CREATE TABLE unavailable_profile(
 horse_id TEXT PRIMARY KEY,horse_name TEXT NOT NULL,profile_url TEXT NOT NULL,error TEXT
);
CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
"""
RE_DATE=re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")

def official_profiles():
    with sqlite3.connect(f"file:{FULL}?mode=ro",uri=True) as c:
        rows=c.execute("""SELECT DISTINCT horse_id,horse_name,horse_profile_url
             FROM runner_postrace WHERE race='京都12R' ORDER BY horse_number""").fetchall()
    if len(rows)!=18:raise ValueError("expected 18 verified Kyoto12 horse profiles")
    return rows

def get(url):
    with urlopen(Request(url,headers={"User-Agent":"Mozilla/5.0","Accept-Language":"ja,en;q=0.8"}),timeout=25) as f:
        return f.read()

def parse_profile(raw,expected_name):
    soup=BeautifulSoup(raw,"html.parser")
    plain=soup.get_text(" ",strip=True)
    if "競走馬情報" not in plain or expected_name not in plain:
        raise ValueError("official profile name/content mismatch")
    tables=[]
    for table in soup.select("table"):
        header=[c.get_text(" ",strip=True) for c in table.select("th")[:20]]
        if "年月日" in header and "着順" in header and "騎手名" in header:
            tables.append(table)
    if len(tables)!=1:raise ValueError("JRA recent-history table missing/duplicate")
    past=[]
    for tr in tables[0].select("tr"):
        cells=tr.find_all(["th","td"],recursive=False)
        vals=[c.get_text(" ",strip=True) for c in cells]
        if len(vals)!=14:continue
        match=RE_DATE.fullmatch(vals[0])
        if not match:continue
        d=dt.date(*map(int,match.groups()))
        if d>=dt.date(2026,11,8):
            # No target-race outcome in the historical prior-race features.
            continue
        def num(s):
            return float(s) if re.fullmatch(r"\d+(?:\.\d+)?",str(s)) else None
        def integer(s):
            return int(s) if re.fullmatch(r"\d+",str(s)) else None
        past.append({
           "prior_race_date":d.isoformat(),"venue":vals[1],
           "race_name":vals[2],"distance_surface":vals[3],"going":vals[4],
           "field_size":integer(vals[5]),"popularity_final":integer(vals[6]),
           "finish_position":integer(vals[7]),"jockey_name":vals[8],
           "assigned_weight_kg":num(vals[9]),"bodyweight_kg":integer(vals[10]),
           "time_text":vals[11],"rating_text":vals[12],"opponent_text":vals[13]})
    return past

def main():
    if OUT.exists():raise FileExistsError("cannot overwrite proven batch")
    profiles=official_profiles()
    results=[]
    for idx,(horse_id,name,url) in enumerate(profiles):
        # Throttle official site access to approximately one page per second.
        if idx>0:time.sleep(1)
        try:
            raw=get(url)
            history=parse_profile(raw,name)
            results.append({"status":"verified","horse_id":horse_id,"horse_name":name,
              "profile_url":url,"sha256":hashlib.sha256(raw).hexdigest(),
              "observed_at":dt.datetime.now(dt.timezone.utc).isoformat(),
              "history":history})
        except Exception as exc:
            results.append({"status":"unavailable","horse_id":horse_id,
               "horse_name":name,"profile_url":url,"error":str(exc)[:500]})
    good=[x for x in results if x["status"]=="verified"]
    if len(good)<12:raise ValueError("too few actual official profiles verified")
    OUT.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(OUT)
    try:
        c.execute("PRAGMA foreign_keys=ON")
        c.executescript(SCHEMA)
        for r in results:
            if r["status"]=="unavailable":
                c.execute("INSERT INTO unavailable_profile VALUES(?,?,?,?)",
                    (r["horse_id"],r["horse_name"],r["profile_url"],r["error"]))
                continue
            c.execute("INSERT INTO official_profile VALUES(?,?,?,?,?,0,0,?)",
                (r["horse_id"],r["horse_name"],r["profile_url"],
                 r["sha256"],r["observed_at"],len(r["history"])))
            for h in r["history"]:
                c.execute("""INSERT OR IGNORE INTO official_past_run VALUES(
                   ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)""",
                   (r["horse_id"],h["prior_race_date"],h["venue"],
                    h["race_name"],h["distance_surface"],h["going"],
                    h["field_size"],h["popularity_final"],h["finish_position"],
                    h["jockey_name"],h["assigned_weight_kg"],h["bodyweight_kg"],
                    h["time_text"],h["rating_text"],h["opponent_text"],
                    r["observed_at"],r["sha256"]))
        for k,v in {"batch":"kyoto12_2026-11-08",
             "same_race_preoff_eligible":"false",
             "usable_for_future_after_capture":"true",
             "publication_time_of_past_races":"not_verified",
             "source":"JRA official horse profile",
             "no_third_party_source":"true"}.items():
            c.execute("INSERT INTO meta VALUES(?,?)",(k,v))
        c.commit()
        if c.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
            raise RuntimeError("SQLite invalid")
        if c.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("foreign key failure")
        count=c.execute("SELECT count(*) FROM official_past_run").fetchone()[0]
    except Exception:
        c.close();OUT.unlink(missing_ok=True);raise
    finally:
        try:c.close()
        except Exception:pass
    audit={"schema":"jra-official-profile-recent-history-v1",
       "source":"JRA official profile pages only",
       "requested_profiles":18,"verified_profiles":len(good),
       "unavailable_profiles":len(results)-len(good),
       "past_race_history_rows":count,
       "sqlite_bytes":OUT.stat().st_size,
       "sqlite_sha256":hashlib.sha256(OUT.read_bytes()).hexdigest(),
       "sqlite_integrity":"ok",
       "first_observed_at_after_2026_11_08_event":True,
       "same_2026_11_08_race_backtest_eligible":False,
       "only_future_forecasts_after_observation_eligible":True,
       "source_published_at_unverified":True,
       "unavailable":[r for r in results if r["status"]=="unavailable"]}
    AUDIT.write_text(json.dumps(audit,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(audit,ensure_ascii=False))
if __name__=="__main__":main()
