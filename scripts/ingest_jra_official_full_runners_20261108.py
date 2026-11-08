"""Create a verified postrace official JRA runner-history companion SQLite.

Official result pages only, 2026-11-08 all 36 races. Do not use postrace
finish, popularity, bodyweight or timing as a preoff feature for THAT race.
Name-only joins to historical horse IDs are forbidden. Never overwrite
Library's canonical v11 while it has unresolved materialization discrepancy.
"""
import concurrent.futures,datetime as dt,hashlib,json,re,sqlite3
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urljoin
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"operations/results/2026-11-08/v50_abcd_settlement.json"
DB=ROOT/"operations/data_updates/jra_official_full_runner_history_20261108.sqlite"
AUDIT=ROOT/"operations/data_updates/jra_official_full_runner_history_20261108_audit.json"
REPORT=ROOT/"reports/v51/JRA_20261108_FULL_RUNNER_HISTORY_ENRICHMENT.md"
def norm(s):return re.sub(r"[\s　・.．]","",s or "")
def raw_get(url):
    req=Request(url,headers={"User-Agent":"Mozilla/5.0 (compatible; legitimate-jra-data-audit/1.0)"})
    with urlopen(req,timeout=22) as fh:return fh.read(),fh.url
def safe_number(v):
    v=v.strip().replace(",","")
    try:return float(v) if v and re.fullmatch(r"\d+(?:\.\d+)?",v) else None
    except ValueError:return None
def get_time(s):
    s=s.strip()
    if not re.fullmatch(r"\d{1,2}:\d{2}\.\d",s):return None
    minute,sec=s.split(":")
    return int(minute)*60+float(sec)
def get_weight(s):
    m=re.search(r"(?<!\d)(\d{3})\s*\(\s*([+-]?\d+)\s*\)",s)
    return (int(m.group(1)),int(m.group(2))) if m else (None,None)

def scrape(r):
    url=r["url"]
    raw,final_url=raw_get(url)
    soup=BeautifulSoup(raw,"html.parser")
    plain=soup.get_text(" ",strip=True)
    if not ("2026年11月8日" in plain and r["track"] in plain):
        raise ValueError(r["race"]+": date/track official validation failed")
    if not re.search(rf"(?<!\d){r['race_number']}R(?!\d)",plain):
        raise ValueError(r["race"]+": race mismatch")
    accepted={int(h["number"]):h for h in r["runners"]}
    all_rows=[]
    for tr in soup.find_all("tr"):
        cells=tr.find_all(["th","td"],recursive=False)
        parts=[c.get_text(" ",strip=True) for c in cells]
        if len(parts)<13 or not re.fullmatch(r"\d{1,2}",parts[0]) or not re.fullmatch(r"\d{1,2}",parts[2]):
            continue
        place=int(parts[0]);num=int(parts[2])
        if num not in accepted:continue
        if place!=int(accepted[num]["finish"]):raise ValueError(r["race"]+": unexpected position")
        named=parts[3]
        original=accepted[num]["name"]
        if norm(original) not in norm(named):
            raise ValueError(r["race"]+": horse-name mismatch "+str(num)+" "+repr(named))
        # Classic JRA result layout (finish, frame, number, horse, sex-age,
        # handicap, rider, time, margin, corner, final3, weight, trainer, pop)
        if len(parts)<14:raise ValueError(r["race"]+": incomplete JRA result columns")
        pop_match=re.search(r"(\d{1,2})番人気",parts[3])
        if not pop_match and re.fullmatch(r"\d{1,2}",parts[-1]):
            pop_match=re.fullmatch(r"\d{1,2}",parts[-1])
        pop=int(pop_match.group(1)) if pop_match else int(accepted[num]["popularity_final"])
        if pop!=int(accepted[num]["popularity_final"]):
            raise ValueError(r["race"]+": popularity mismatch")
        # Horse profile anchors are NOT assumed to provide an ID if not explicit.
        horse_id=None;horse_profile_url=None
        for a in cells[3].select("a[href]"):
            href=urljoin(final_url,a["href"])
            m=re.search(r"pw01dud10(\d{10})",href)
            if m and norm(a.get_text(" ",strip=True))==norm(original):
                horse_id="jra:"+m.group(1);horse_profile_url=href;break
        bw,delta=get_weight(parts[11])
        corner=[int(x) for x in re.findall(r"\b\d{1,2}\b",parts[9])]
        all_rows.append({"horse_number":num,"horse_name":original,"finish":place,
              "popularity_final":pop,
              "sex_age":parts[4],"carried_weight":safe_number(parts[5]),
              "jockey":parts[6],"time_sec":get_time(parts[7]),
              "margin":parts[8],"corner_positions":corner,
              "last3_sec":safe_number(parts[10]),"bodyweight":bw,"bodyweight_delta":delta,
              "trainer":parts[12],"horse_id":horse_id,
              "horse_profile_url":horse_profile_url})
    all_rows.sort(key=lambda x:(x["finish"],x["horse_number"]))
    # Some JRA races include non-finishers. The archived result parser may
    # contain only numeric finishers: require exact equivalence to the archived
    # number+finish+name set before certifying completed result coverage.
    observed={(x["horse_number"],x["finish"]) for x in all_rows}
    expected={(x["number"],x["finish"]) for x in r["runners"]}
    if observed!=expected:
        samples=[]
        for tr in soup.find_all("tr"):
            cells=tr.find_all(["td","th"],recursive=False)
            parts=[c.get_text(" ",strip=True) for c in cells]
            if len(parts)>=4 and re.fullmatch(r"\d{1,2}",parts[0]) and re.fullmatch(r"\d{1,2}",parts[2]):
                samples.append({"len":len(parts),"head":parts[:14]})
            if len(samples)>=2:break
        raise ValueError(r["race"]+": full runner roster differs archived "+
            repr({"observed_n":len(observed),"expected_n":len(expected),
                  "missing":sorted(expected-observed)[:4],"sample":samples})[:800])
    if [x["horse_number"] for x in all_rows[:3]]!=r["top3_numbers"]:
        raise ValueError(r["race"]+": podium differs")
    return {"race":r["race"],"race_date":"2026-11-08","venue":r["track"],
      "race_number":r["race_number"],"source_url":final_url,
      "content_sha256":hashlib.sha256(raw).hexdigest(),
      "observed_at":dt.datetime.now(dt.timezone.utc).isoformat(),
      "surface":r["surface"],"going":r["going"],"runners":all_rows}

def main():
    if DB.exists():raise FileExistsError("no overwrite of archived official history")
    d=json.loads(SOURCE.read_text())
    results=d["official"]
    if len(results)!=36 or any(r["status"]!="official_verified" for r in results):
        raise ValueError("36 archived JRA results not available")
    checked=[];fail=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        fut={pool.submit(scrape,r):r for r in results}
        for f,r in fut.items():
            try:checked.append(f.result())
            except Exception as e:fail.append({"race":r["race"],"error":str(e)[:300]})
    # To avoid discarding verified data, each race failure is explicitly
    # quarantined in the audit. Do not falsely claim 36/36 completion.
    DB.parent.mkdir(parents=True,exist_ok=True)
    conn=sqlite3.connect(DB)
    try:
        conn.executescript("""
        PRAGMA foreign_keys=ON;
        CREATE TABLE source_race(
          race_id TEXT PRIMARY KEY,race_date TEXT NOT NULL,venue TEXT NOT NULL,
          race_number INTEGER NOT NULL,surface TEXT,going TEXT,
          official_url TEXT NOT NULL,sha256 TEXT NOT NULL,observed_at TEXT NOT NULL,
          retrospectively_label_only INTEGER NOT NULL CHECK(retrospectively_label_only=1));
        CREATE TABLE source_runner(
          race_id TEXT NOT NULL,horse_number INTEGER NOT NULL,horse_name TEXT NOT NULL,
          official_horse_id TEXT,horse_profile_url TEXT,
          finish INTEGER NOT NULL,popularity_final INTEGER NOT NULL,
          sex_age TEXT,carried_weight REAL,jockey TEXT,
          time_seconds REAL,margin TEXT,corner_positions_json TEXT,
          last3_seconds REAL,bodyweight_kg INTEGER,bodyweight_delta_kg INTEGER,
          trainer TEXT,preoff_usable_for_same_race INTEGER NOT NULL CHECK(preoff_usable_for_same_race=0),
          PRIMARY KEY(race_id,horse_number),
          FOREIGN KEY(race_id) REFERENCES source_race(race_id));
        CREATE TABLE source_error(race_id TEXT PRIMARY KEY,reason TEXT NOT NULL);
        CREATE INDEX idx_official_runner_name ON source_runner(horse_name);
        CREATE INDEX idx_official_runner_horse_id ON source_runner(official_horse_id);
        """)
        for r in checked:
            conn.execute("INSERT INTO source_race VALUES(?,?,?,?,?,?,?,?,?,1)",
                (r["race"],r["race_date"],r["venue"],r["race_number"],
                 r["surface"],r["going"],r["source_url"],r["content_sha256"],r["observed_at"]))
            for h in r["runners"]:
                conn.execute("INSERT INTO source_runner VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0)",
                    (r["race"],h["horse_number"],h["horse_name"],h["horse_id"],h["horse_profile_url"],
                     h["finish"],h["popularity_final"],h["sex_age"],h["carried_weight"],
                     h["jockey"],h["time_sec"],h["margin"],
                     json.dumps(h["corner_positions"]),h["last3_sec"],h["bodyweight"],
                     h["bodyweight_delta"],h["trainer"]))
        for x in fail:conn.execute("INSERT INTO source_error VALUES(?,?)",(x["race"],x["error"]))
        conn.commit()
        if conn.execute("PRAGMA integrity_check").fetchone()[0]!="ok" or conn.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("SQLite not integral")
        count=dict(conn.execute("SELECT 'races',count(*) FROM source_race UNION ALL SELECT 'runners',count(*) FROM source_runner UNION ALL SELECT 'horse_ids',count(*) FROM source_runner WHERE official_horse_id IS NOT NULL UNION ALL SELECT 'times',count(*) FROM source_runner WHERE time_seconds IS NOT NULL UNION ALL SELECT 'last3',count(*) FROM source_runner WHERE last3_seconds IS NOT NULL UNION ALL SELECT 'jockeys',count(*) FROM source_runner WHERE jockey IS NOT NULL"))
    finally:conn.close()
    binary=DB.read_bytes()
    audit={"schema":"official-jra-20261108-full-runner-history-v1",
        "sqlite_sha256":hashlib.sha256(binary).hexdigest(),"sqlite_size_bytes":len(binary),
        "sqlite_integrity":"ok","races_attempted":len(results),
        "counts":count,"failed_races":fail,
        "unverified_horse_id_rows_not_inferred":True,
        "retrospective_use_only_for_2026_11_08":True,
        "base_canonical_v11_not_modified":True,
        "all_sources_official":True}
    AUDIT.write_text(json.dumps(audit,ensure_ascii=False,indent=2)+"\n")
    lines=["# JRA公式・2026-11-08 全頭結果履歴DB増強","",
       "JRA公式結果から、全頭の馬名・馬番・騎手・斤量・タイム・通過・上がり・馬体重を取得したレースのみ保存。",
       "出走後観測データ。対象日の発走前V50/V51に混ぜない。","",
       f"試行36R／公式結果照合成功{count['races']}R／出走馬{count['runners']}行。",
       f"公式馬IDがURLから厳密に取得できた行{count['horse_ids']}件。",
       f"走破タイム{count['times']}件、上がり{count['last3']}件、騎手{count['jockeys']}件。",
       f"未取込レース：{fail}","",
       "元のLibrary v11は破損疑義により上書きしない。GitHubの独立した追加SQLiteに格納。",
       "保存後のSQLite整合性検査を成功したもののみ採用。",""]
    REPORT.parent.mkdir(parents=True,exist_ok=True);REPORT.write_text("\n".join(lines)+"\n")
    print(json.dumps({"counts":count,"failed":fail,"sha256":audit["sqlite_sha256"]},ensure_ascii=False))

if __name__=="__main__":main()
