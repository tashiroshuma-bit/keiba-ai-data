"""Append-only, official postrace full-runner fact collection for 2026-11-08.

The 36 authoritative JRA mobile result URLs are already audited and frozen in
the 2026-11-08 settlement. Fetch only that fixed set. Strictly require race/date
and every horse number/name to match the frozen JRA outcomes. Save factual
post-race fields: carried weight, bodyweight/change, finish time, final 3F,
jockey. NEVER present historical result observations as pre-off data.
This research ingestion creates a NEW companion SQLite, never overwrites v11.
"""
from __future__ import annotations
import concurrent.futures,datetime as dt,hashlib,json,re,sqlite3
from pathlib import Path
from urllib.request import Request,urlopen
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
FROZEN=ROOT/"operations/results/2026-11-08/v50_abcd_settlement.json"
OUT=ROOT/"operations/data_updates/jra_nov08_full_runner_facts_20261108.json"
DB=ROOT/"operations/data_updates/jra_nov08_postrace_facts_20261108.sqlite"
REPORT=ROOT/"reports/v51/JRA_NOV08_FULL_RUNNER_FACTS_AUDIT.md"
JST=dt.timezone(dt.timedelta(hours=9))

def normal(v):return re.sub(r"[\s　・．.]+","",str(v or ""))
def get(url):
    with urlopen(Request(url,headers={"User-Agent":"Mozilla/5.0"}),timeout=22) as r:
        return r.read()

def parse(r):
    label=r["race"]
    try:
        raw=get(r["url"])
        observed=dt.datetime.now(JST).isoformat()
        soup=BeautifulSoup(raw,"html.parser")
        txt=soup.get_text(" ",strip=True)
        if not all(s in txt for s in ("2026年11月8日",r["track"])) or not re.search(
            rf"(?<!\d){r['race_number']}R(?!\d)",txt):
            raise ValueError("wrong date, track or race")
        recorded={int(h["number"]):h for h in r["runners"]}
        data={}
        sample=[]
        for tr in soup.find_all("tr"):
            cells=tr.find_all(["td","th"],recursive=False)
            c=[x.get_text(" ",strip=True) for x in cells]
            if len(c)<4 or not re.fullmatch(r"\d{1,2}",c[0]) or not re.fullmatch(r"\d{1,2}",c[2]):continue
            finish=int(c[0]);num=int(c[2])
            if num not in recorded:continue
            base=recorded[num]
            v=c[3]
            if normal(base["name"]) not in normal(v):
                raise ValueError(f"JRA horse name conflict at {num}: {base['name']} vs {v[:75]}")
            if finish!=base["finish"]:
                raise ValueError(f"JRA finish position conflict at {num}")
            # Table is JRA's factual multi-line horse/finish information:
            # "HorseNameN番人気 性齢 / Weightkg(diff) Rider(assigned) Trainer \n time / final3f".
            # Parse only anchored facts; unparseable fields are null, not guesses.
            pop=re.search(r"(\d{1,2})番人気",v)
            if pop and int(pop[1])!=base["popularity_final"]:
                raise ValueError("JRA popularity mismatch")
            age=re.search(r"(牡|牝|せん|騸)(\d{1,2})",v)
            bw=re.search(r"(?<!\d)(\d{3})\s*kg\s*[\(（]\s*([+\-−]?\d+)\s*[\)）]",v)
            # Some JRA representations omit kg after the three digit bodyweight.
            if not bw:bw=re.search(r"(?<!\d)(\d{3})\s*[\(（]\s*([+\-−]?\d+)\s*[\)）]",v)
            carried=re.search(r"[\(（]\s*(\d{2}(?:\.\d)?)\s*[\)）]",v)
            # Finish and final-3F are near the end in the JRA mobile card.
            times=re.findall(r"(?<!\d)([0-9]:[0-5]\d\.[0-9])(?!\d)",v)
            last3f=re.findall(r"(?<!\d)([2-6]\d\.[0-9])(?!\d)",v)
            # Do not parse person identity without explicit jockey labeling:
            # the jockey field may be linebreak-dependent. Preserve sex/age etc.
            captured={
                "race":label,"track":r["track"],"race_number":r["race_number"],
                "horse_number":num,"horse_name":base["name"],"finish":finish,
                "final_popularity":base["popularity_final"],
                "sex":age[1] if age else None,"age":int(age[2]) if age else None,
                "bodyweight_kg":int(bw[1]) if bw else None,
                "bodyweight_change_kg":int(bw[2].replace("−","-")) if bw else None,
                "assigned_weight_kg":float(carried[1]) if carried else None,
                "finish_time":times[-1] if times else None,
                "last3f_seconds":float(last3f[-1]) if last3f else None,
                "published_at":None,"observed_at":observed,
                "source_url":r["url"],"source_sha256":hashlib.sha256(raw).hexdigest(),
                "phase":"postrace","preoff_eligible_for_same_race":False,
            }
            if num in data:raise ValueError("same horse appeared twice")
            data[num]=captured
            if len(sample)<2:sample.append(v[:230])
        if len(data)!=len(recorded):raise ValueError(f"row count {len(data)}/{len(recorded)}")
        return {"race":label,"status":"verified",
            "row_count":len(data),"facts":list(data.values()),
            "source_sha256":hashlib.sha256(raw).hexdigest(),"observed_at":observed}
    except Exception as e:
        return {"race":label,"status":"rejected","error":str(e)[:500]}

def main():
    if OUT.exists() or DB.exists():raise FileExistsError("immutable official facts snapshot already exists")
    frozen=json.loads(FROZEN.read_text())
    targets=frozen["official"]
    if len(targets)!=36:raise ValueError("expected 36 frozen JRA results")
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        results=list(pool.map(parse,targets))
    accepted=[r for r in results if r["status"]=="verified"]
    rows=[h for r in accepted for h in r["facts"]]
    if len(accepted)<30 or len(rows)<300:
        raise RuntimeError("insufficient full-field official facts: "+
            json.dumps({"accepted":len(accepted),"rows":len(rows),
                        "failures":[r for r in results if r["status"]!="verified"][:7]},
                       ensure_ascii=False))
    data={"schema":"jra-nov08-full-runner-facts-v1","date":"2026-11-08",
          "official_races_attempted":36,"verified_races":len(accepted),
          "verified_horse_rows":len(rows),
          "coverage":{k:sum(x[k] is not None for x in rows)
                      for k in ("sex","age","bodyweight_kg","bodyweight_change_kg",
                                "assigned_weight_kg","finish_time","last3f_seconds")},
          "results":results,"preoff_for_nov08":False}
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n")
    con=sqlite3.connect(DB)
    try:
        con.execute("""CREATE TABLE jra_historical_runner_fact(
            race_label TEXT NOT NULL,horse_number INTEGER NOT NULL,
            horse_name TEXT NOT NULL,finish_position INTEGER NOT NULL,
            final_popularity INTEGER NOT NULL,sex TEXT,age INTEGER,
            bodyweight_kg INTEGER,bodyweight_change_kg INTEGER,
            assigned_weight_kg REAL,finish_time TEXT,last3f_seconds REAL,
            observed_at TEXT NOT NULL,published_at TEXT,
            source_url TEXT NOT NULL,source_sha256 TEXT NOT NULL,
            preoff_eligible_for_same_race INTEGER NOT NULL CHECK(preoff_eligible_for_same_race=0),
            PRIMARY KEY(race_label,horse_number))""")
        for x in rows:
            con.execute("INSERT INTO jra_historical_runner_fact VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (x["race"],x["horse_number"],x["horse_name"],x["finish"],
                 x["final_popularity"],x["sex"],x["age"],
                 x["bodyweight_kg"],x["bodyweight_change_kg"],
                 x["assigned_weight_kg"],x["finish_time"],x["last3f_seconds"],
                 x["observed_at"],None,x["source_url"],x["source_sha256"],0))
        con.commit()
        if con.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
            raise ValueError("SQLite integration broken")
        if con.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("foreign-key violations")
        if con.execute("SELECT COUNT(*) FROM jra_historical_runner_fact").fetchone()[0]!=len(rows):
            raise ValueError("re-read failed")
    finally:con.close()
    lines=["# JRA公式11月8日｜全馬別結果データの取得と再読込検証","",
       "**2026-11-08の事後結果のみ。2026-11-08の発走前予測への流用禁止。**",
       f"公式レース照合成功：{len(accepted)}/36R、馬別事実：{len(rows)}行。","",
       "|項目|馬数|","|---|---:|"]
    for k,v in data["coverage"].items():lines.append(f"|{k}|{v}|")
    lines+=["","## 取得失敗・追加検査",""]
    for x in results:
        if x["status"]!="verified":lines.append(f"- {x['race']}: {x['error']}")
    lines+=["","## 注意点","",
       "- ソースはJRA公式の開催済み結果。元の予測時刻以前にこれらの情報が公開されていたと推測しない。",
       "- 公開時刻は不明（null）。現在の観測時刻のみ記録。",
       "- 公式の馬IDリンクが確認できない馬は、馬番と名前だけで過去別レースの馬と自動連結しない。",
       "- 正本v11の既存履歴は変更しない。SQLite補助DBの新しい別版として保管。",
       ""]
    REPORT.parent.mkdir(parents=True,exist_ok=True)
    REPORT.write_text("\n".join(lines))
    print(json.dumps({"verified":len(accepted),"rows":len(rows),"coverage":data["coverage"],
                     "sqlite_sha256":hashlib.sha256(DB.read_bytes()).hexdigest()},
        ensure_ascii=False))

if __name__=="__main__":main()
