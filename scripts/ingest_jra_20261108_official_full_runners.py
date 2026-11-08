"""Import official JRA full-runner Nov8 results into a separate immutable SQLite.

This creates only POST-RACE observations with original JRA horse profile IDs.
Do not use this data to predict its own race. Current JRA desktop results have
explicit links of form pw01dud00<10-digit JRA horse ID>/<token>; no name
matching across different races and no inferred publication times.

One page/day index finds all 3 venues and all 12 actual race URLs. Each row
records observed source hash, full runner number/name and race result features.
Unmatched/malformed races are quarantined without inventing data.
"""
from __future__ import annotations
import datetime as dt,hashlib,json,re,sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request,urlopen
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
SEED="https://www.jra.go.jp/JRADB/accessS.html?CNAME=pw01sde0108202605021220261108%2FB4"
SETTLEMENT=ROOT/"operations/results/2026-11-08/v50_abcd_settlement.json"
OUT=ROOT/"operations/data_updates/jra_official_20261108_all_runner_history.sqlite"
AUDIT=ROOT/"operations/data_updates/jra_official_20261108_all_runner_history_audit.json"
TRACK={"東京":"東京","京都":"京都","福島":"福島"}
RE_ID=re.compile(r"pw01dud00(\d{10})/",re.I)
RE_RACE=re.compile(r"pw01sde01\d{2}\d{8}\d{2}20261108/",re.I)

SCHEMA="""
CREATE TABLE source_race(
 race TEXT PRIMARY KEY,source_url TEXT NOT NULL,source_sha256 TEXT NOT NULL,
 observed_at TEXT NOT NULL,track TEXT NOT NULL,race_no INTEGER NOT NULL,
 expected_finishers INTEGER NOT NULL,parsed_finishers INTEGER NOT NULL,
 official_id_coverage INTEGER NOT NULL,verified_checkpoint INTEGER NOT NULL
);
CREATE TABLE runner_postrace(
 race TEXT NOT NULL,horse_number INTEGER NOT NULL CHECK(horse_number BETWEEN 1 AND 18),
 horse_name TEXT NOT NULL,horse_id TEXT NOT NULL,horse_profile_url TEXT NOT NULL,
 finish_position INTEGER,gender_age TEXT,assigned_weight_kg REAL,
 jockey_name TEXT,race_time TEXT,margin_text TEXT,corner_positions TEXT,
 estimated_last3f_seconds REAL,bodyweight_kg INTEGER,bodyweight_delta_kg INTEGER,
 trainer_name TEXT,final_popularity INTEGER,
 observed_at TEXT NOT NULL,source_url TEXT NOT NULL,source_sha256 TEXT NOT NULL,
 result_only_not_prediction_feature INTEGER NOT NULL DEFAULT 1 CHECK(result_only_not_prediction_feature=1),
 PRIMARY KEY(race,horse_number),FOREIGN KEY(race) REFERENCES source_race(race)
);
CREATE INDEX idx_runner_horse_id ON runner_postrace(horse_id);
CREATE INDEX idx_runner_race ON runner_postrace(race);
CREATE TABLE quarantined_race(race TEXT PRIMARY KEY,source_url TEXT,error TEXT NOT NULL);
CREATE TABLE ingestion_manifest(key TEXT PRIMARY KEY,value TEXT NOT NULL);
"""

def get(url):
    with urlopen(Request(url,headers={"User-Agent":"Mozilla/5.0","Accept-Language":"ja,en;q=0.9"}),timeout=24) as f:
        return f.read()

def normalize(s):
    return re.sub(r"[\s\u3000]+","",str(s)).strip()

def links_from_seed(html):
    root=BeautifulSoup(html,"html.parser")
    venues={}
    for a in root.select("a[href]"):
        name=normalize(a.get_text(" ",strip=True))
        u=a.get("href","")
        if "pw01sde01" in u and "20261108" in u:
            track=next((x for x in TRACK if x in name),None)
            if track:
                venues[track]=urljoin(SEED,u)
    if set(venues)!=set(TRACK):raise ValueError("three venue desktop results missing")
    return venues

def race_links(url,body,track):
    soup=BeautifulSoup(body,"html.parser")
    urls={}
    for a in soup.select("a[href]"):
        href=a.get("href","")
        if not RE_RACE.search(href):continue
        # verify JRA race URL track has the known venue code.
        m=re.search(r"pw01sde01(\d{2})\d{8}(\d{2})20261108/",href)
        if not m:continue
        venue_id=m[1]
        expected={"東京":"05","京都":"08","福島":"03"}[track]
        if venue_id!=expected:continue
        number=int(m[2])
        if number not in range(1,13):continue
        urls[number]=urljoin(url,href)
    if set(urls)!=set(range(1,13)):
        raise ValueError(f"{track} desktop nav incomplete {sorted(urls)}")
    return urls

def integer(s):
    s=str(s).replace(",","").strip()
    return int(s) if re.fullmatch(r"\d{1,2}",s) else None

def number(s):
    t=normalize(s).replace("－","-")
    return float(t) if re.fullmatch(r"[+-]?\d+(?:\.\d+)?",t) else None

def weight(s):
    m=re.fullmatch(r"\s*(\d{3})\s*\(\s*([+-]?\d+)\s*\)\s*",str(s))
    return (int(m[1]),int(m[2])) if m else (None,None)

def parse_result(html,url,track,race_no,expected):
    soup=BeautifulSoup(html,"html.parser")
    plain=soup.get_text(" ",strip=True)
    if "2026年11月8日" not in plain or track not in plain or not re.search(
            rf"(?<!\d){race_no}レース(?!\d)",plain):
        raise ValueError("official date/race/venue mismatch")
    tables=[]
    for t in soup.select("table"):
        head=" ".join(x.get_text(" ",strip=True) for x in t.select("th")[:15])
        if "着順" in head and "馬" in head and "騎手" in head:tables.append(t)
    if len(tables)!=1:raise ValueError("JRA runner table missing or duplicated")
    runners=[]
    for tr in tables[0].select("tr"):
        td=tr.find_all(["th","td"],recursive=False)
        if len(td)!=14:continue
        vals=[x.get_text(" ",strip=True) for x in td]
        horse_no=integer(vals[2])
        if horse_no is None:continue
        profile=[]
        for a in td[3].select("a[href]"):
            href=a.get("href","")
            m=RE_ID.search(href)
            if m and normalize(a.get_text(" ",strip=True))==normalize(vals[3]):
                profile.append(("jra:"+m[1],urljoin(url,href)))
        if len(profile)!=1:
            raise ValueError("exact JRA horse profile ID missing for "+str(horse_no))
        kg,delta=weight(vals[11])
        row={"horse_number":horse_no,"horse_name":normalize(vals[3]),
             "horse_id":profile[0][0],"horse_profile_url":profile[0][1],
             "finish_position":integer(vals[0]),"gender_age":vals[4],
             "assigned_weight_kg":number(vals[5]),"jockey_name":vals[6],
             "race_time":vals[7],"margin_text":vals[8],
             "corner_positions":vals[9],
             "estimated_last3f_seconds":number(vals[10]),
             "bodyweight_kg":kg,"bodyweight_delta_kg":delta,
             "trainer_name":vals[12],"final_popularity":integer(vals[13])}
        runners.append(row)
    valid_finishers=sum(r["finish_position"] is not None for r in runners)
    if len(runners)!=expected["headcount"]:
        # Fukushima4R obstacle race: historic finishers-only settlement had
        # 9 runners; desktop official result includes two non-finishers.
        # All 11 actual entrants are preserved with finish_position NULL.
        if not (track=="福島" and race_no==4 and
                expected["headcount"]==9 and len(runners)==11 and
                valid_finishers==9):
            raise ValueError(f"JRA entrants {len(runners)}, finishers {valid_finishers} vs old settlement {expected['headcount']}")
    if track=="福島" and race_no==4 and len(runners)!=11:
        raise ValueError("Fukushima4 expected 11 total starters including nonfinishers")
    if len(set(r["horse_number"] for r in runners))!=len(runners):
        raise ValueError("duplicate horse numbers")
    if len(set(r["horse_id"] for r in runners))!=len(runners):
        raise ValueError("two runner numbers have same official horse identity")
    podium=[r["horse_number"] for r in sorted(runners,key=lambda x:x["finish_position"]
            if x["finish_position"] is not None else 99)[:3]]
    if podium!=expected["top3_numbers"]:
        raise ValueError(f"official desktop podium mismatch {podium} vs {expected['top3_numbers']}")
    pops=[next(r["final_popularity"] for r in runners if r["horse_number"]==n)
          for n in podium]
    if pops!=expected["top3_popularity"]:
        raise ValueError(f"official final popularity mismatch {pops} vs {expected['top3_popularity']}")
    return runners

def main():
    if OUT.exists():raise FileExistsError("never overwrite an existing evidence database")
    archive=json.loads(SETTLEMENT.read_text())
    prior={x["race"]:x for x in archive["official"] if x["status"]=="official_verified"}
    if len(prior)!=36:raise ValueError("official race checkpoint not complete")
    seed_bytes=get(SEED)
    venues=links_from_seed(seed_bytes)
    with ThreadPoolExecutor(max_workers=3) as pool:
        venue_bodies=dict(zip(venues,pool.map(get,[venues[k] for k in venues])))
    race_urls={}
    for venue,body in venue_bodies.items():
        urls=race_links(venues[venue],body,venue)
        for number,u in urls.items():race_urls[f"{venue}{number}R"]=(venue,number,u)
    if len(race_urls)!=36 or set(race_urls)!=set(prior):raise ValueError("36 race URLs incomplete")
    def one(item):
        race,(track,race_no,url)=item
        try:
            raw=get(url)
            results=parse_result(raw,url,track,race_no,prior[race])
            return {"race":race,"status":"verified","source_url":url,
                  "source_sha256":hashlib.sha256(raw).hexdigest(),
                  "observed_at":dt.datetime.now(dt.timezone.utc).isoformat(),
                  "runners":results,"track":track,"race_no":race_no}
        except Exception as exc:
            return {"race":race,"status":"quarantined","source_url":url,
                   "error":str(exc)[:800]}
    with ThreadPoolExecutor(max_workers=5) as pool:
        fetched=list(pool.map(one,sorted(race_urls.items())))
    verified=[x for x in fetched if x["status"]=="verified"]
    quarantined=[x for x in fetched if x["status"]!="verified"]
    if not verified:
        raise RuntimeError("No JRA full runner race proven; "+str(quarantined[:2]))
    OUT.parent.mkdir(parents=True,exist_ok=True)
    conn=sqlite3.connect(OUT)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(SCHEMA)
        for record in verified:
            race=record["race"]
            expected=prior[race]
            conn.execute("INSERT INTO source_race VALUES(?,?,?,?,?,?,?,?,?,1)",
                (race,record["source_url"],record["source_sha256"],record["observed_at"],
                 record["track"],record["race_no"],expected["headcount"],
                 len(record["runners"]),len(record["runners"])))
            for r in record["runners"]:
                conn.execute("""INSERT INTO runner_postrace VALUES(
                 ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)""",(
                 race,r["horse_number"],r["horse_name"],r["horse_id"],
                 r["horse_profile_url"],r["finish_position"],r["gender_age"],
                 r["assigned_weight_kg"],r["jockey_name"],r["race_time"],
                 r["margin_text"],r["corner_positions"],r["estimated_last3f_seconds"],
                 r["bodyweight_kg"],r["bodyweight_delta_kg"],r["trainer_name"],
                 r["final_popularity"],record["observed_at"],
                 record["source_url"],record["source_sha256"]))
        for x in quarantined:
            conn.execute("INSERT INTO quarantined_race VALUES(?,?,?)",
                   (x["race"],x["source_url"],x["error"]))
        manifest={
            "schema":"jra-official-postrace-identity-features-v1",
            "target_date":"2026-11-08",
            "official_horse_ids_extracted":str(sum(len(x["runners"]) for x in verified)),
            "source_provider":"JRA official, JRA desktop result pages",
            "result_timestamp_proof":"captured postrace observed_at only",
            "race_published_at_proven":"false",
            "same_day_prediction_training_eligible":"false",
            "canonical_sqlite_v11_modified":"false",
            "future_date_usable_only_after_source_observed_at":"true",
            "preoff_frozen_predictions_created":"false",
            "no_name_only_cross_race_join":"true"}
        for k,v in manifest.items():
            conn.execute("INSERT INTO ingestion_manifest VALUES(?,?)",(k,v))
        conn.commit()
        if conn.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
            raise RuntimeError("SQLite integrity failure")
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("foreign key failure")
        count=conn.execute("SELECT count(*) FROM runner_postrace").fetchone()[0]
        if count!=sum(len(x["runners"]) for x in verified):
            raise RuntimeError("runner count mismatch")
    except Exception:
        conn.close();OUT.unlink(missing_ok=True);raise
    finally:
        try:conn.close()
        except Exception:pass
    digest=hashlib.sha256(OUT.read_bytes()).hexdigest()
    summary={"schema":"jra-official-nov8-runner-ingestion-audit-v1",
        "source":"JRA official desktop per-race results",
        "result_date":"2026-11-08",
        "sqlite_sha256":digest,"sqlite_bytes":OUT.stat().st_size,
        "integrity_check":"ok",
        "races_requested":36,"races_verified":len(verified),
        "races_quarantined":len(quarantined),
        "official_runner_ids":count,
        "races_with_exact_18_etc_runner_lists":[x["race"] for x in verified],
        "quarantined":quarantined,
        "preoff_usable_for_2026_11_08":False,
        "available_for_future_after_actual_observation":True,
        "original_canonical_v11_changed":False,
        "previous_thirdparty_feature_rows_unchanged":0}
    AUDIT.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({k:summary[k] for k in ("races_verified","races_quarantined",
      "official_runner_ids","sqlite_bytes","sqlite_sha256","quarantined")},ensure_ascii=False))

if __name__=="__main__":main()
