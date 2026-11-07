"""Historic JRA official full finish and popularity: outsider top-three study.

2026-10-31 and 2026-11-01 official result URLs are frozen in settlement.
A race with missing or malformed actual final popularities is excluded.
Post-race popularity cannot be used for forecasts retroactively.
"""
from __future__ import annotations
import concurrent.futures,datetime as dt,hashlib,json,re,math
from collections import defaultdict,Counter
from pathlib import Path
from urllib.request import urlopen,Request
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
SOURCES=[
 ROOT/"operations/results/2026-10-31/four_model_settlement_20261031T192204+0900.json",
 ROOT/"operations/results/2026-11-01/four_model_settlement_20261101T194949+0900.json",
]
OUT=ROOT/"reports/outsider_top3_20261031_1101_results.json"
REPORT=ROOT/"reports/outsider_top3_20261031_1101_report.md"

def get(url):
    with urlopen(Request(url,headers={"User-Agent":"Mozilla/5.0 (compatible; JRA-official-public-race-research/1.0)"}),timeout=22) as fh:
        return fh.read()

def extract(date,source):
    url=source["source_url"]
    raw=get(url)
    soup=BeautifulSoup(raw,"html.parser")
    text=soup.get_text(" ",strip=True)
    if "2026年" not in text and "2026/" not in text:
        raise ValueError("official year missing")
    runners=[]
    for tr in soup.find_all("tr"):
        cells=[c.get_text(" ",strip=True) for c in tr.find_all(["th","td"],recursive=False)]
        if len(cells)<4 or not (re.fullmatch(r"\d{1,2}",cells[0]) and
                              re.fullmatch(r"\d{1,2}",cells[2])):
            continue
        finish,num=int(cells[0]),int(cells[2])
        pop=None
        if len(cells)>=14 and re.fullmatch(r"\d{1,2}",cells[-1]):
            pop=int(cells[-1])
        if pop is None:
            m=re.search(r"(?<!\d)(\d{1,2})番人気",cells[3])
            if m:pop=int(m[1])
        if pop is None:continue
        runners.append({"finish":finish,"number":num,"popularity_final":pop,
                        "horse_name":cells[3].split(" ")[0][:30]})
    if len(runners)<3:raise ValueError("no result popularity rows")
    actual=[h for h in runners if h["finish"] in (1,2,3)]
    actual.sort(key=lambda x:x["finish"])
    if len(actual)!=3 or [x["finish"] for x in actual]!=[1,2,3]:
        raise ValueError("top-three finish malformed")
    if [[h["finish"],h["number"]] for h in actual]!=source["top3"]:
        raise ValueError("official top3 changed from verified frozen results")
    pop=[h["popularity_final"] for h in runners]
    if len(set(pop))!=len(pop) or sorted(pop)!=list(range(1,len(pop)+1)):
        raise ValueError("all runner final popularity ranks not contiguous")
    if max(h["number"] for h in runners)>18:raise ValueError("horse number exceeds JRA maximum")
    if len({h["number"] for h in runners})!=len(runners):
        raise ValueError("duplicate horse number")
    n=len(runners)
    # Official page text usually includes surface and 1,000 to 3,600m.
    track=source["race"].replace(re.search(r"\d+R",source["race"]).group(0),"")
    surface="unknown"
    title=" ".join((soup.title.get_text(" ",strip=True) if soup.title else "").split())
    head=(title+" "+text[:1200])
    for pat,name in ((r"芝\s*(?:右|左|直)?\s*\d[\d,]{2,4}\s*[ｍm]", "turf"),
                     (r"(?:ダート|ダ)\s*(?:右|左)?\s*\d[\d,]{2,4}\s*[ｍm]","dirt")):
        if re.search(pat,head):surface=name;break
    ranks=[h["popularity_final"] for h in actual]
    return {"date":date,"race":source["race"],"track":track,"surface":surface,
        "field_size":n,"top3_popularity":ranks,
        "top3_numbers":[h["number"] for h in actual],
        "top3_names":[h["horse_name"] for h in actual],
        "any_outsider_top3":any(p>=4 for p in ranks),
        "third_outsider":ranks[2]>=4,
        "outsider_2nd":ranks[1]>=4,
        "outsider_winner":ranks[0]>=4,
        "outsider_count_top3":sum(p>=4 for p in ranks),
        "actual_popularity_full_field":pop,
        "official_result_url":url,
        "source_sha256":hashlib.sha256(raw).hexdigest()}

def stats(rows):
    n=len(rows)
    return {"n":n,
       "any_outsider_top3_count":sum(r["any_outsider_top3"] for r in rows),
       "any_outsider_top3_rate":sum(r["any_outsider_top3"] for r in rows)/n if n else None,
       "third_outsider_count":sum(r["third_outsider"] for r in rows),
       "third_outsider_rate":sum(r["third_outsider"] for r in rows)/n if n else None,
       "outsider_2nd_count":sum(r["outsider_2nd"] for r in rows),
       "outsider_winner_count":sum(r["outsider_winner"] for r in rows),
       "mean_outsider_count_top3":sum(r["outsider_count_top3"] for r in rows)/n if n else None}

def fieldband(n):
    return "3–9" if n<=9 else ("10–13" if n<=13 else "14–18")
def group(rows,key):
    d=defaultdict(list)
    for r in rows:d[key(r)].append(r)
    return {k:stats(v) for k,v in sorted(d.items())}

def main():
    sources=[]
    for file in SOURCES:
        payload=json.loads(file.read_text())
        if payload.get("jra_official_all_24_verified") is not True:
            raise ValueError("unverified official source")
        if len(payload["official_sources"])!=24:
            raise ValueError("not 24 official results in each daily archive")
        sources.extend((payload["date"],r) for r in payload["official_sources"])
    with concurrent.futures.ThreadPoolExecutor(max_workers=7) as pool:
        responses=list(pool.map(lambda pair:guard(*pair),sources))
    rows=[r for r in responses if "error" not in r]
    failures=[r for r in responses if "error" in r]
    # Report missing by source; never treat missing popularity as first 3.
    if len(rows)<20:raise ValueError("too few official 3-place rows: "+str(len(rows))+" failures:"+str(failures[:3]))
    groupby={
        "date":group(rows,lambda r:r["date"]),
        "track":group(rows,lambda r:r["track"]),
        "field_size":group(rows,lambda r:fieldband(r["field_size"])),
        "surface":group(rows,lambda r:r["surface"]),
        "favorite_won":group(rows,lambda r:"1番人気が勝利" if r["top3_popularity"][0]==1 else "1番人気は勝利せず")
    }
    third_pops=Counter(r["top3_popularity"][2] for r in rows)
    all_outside_pops=Counter(pop for r in rows for pop in r["top3_popularity"] if pop>=4)
    result={"schema":"jra-2026-10-31-11-01-official-top3-final-popularity-v1",
        "official_source_count":len(sources),"successful":len(rows),
        "excluded":len(failures),"failures":failures,
        "strictly_post_race_popularity":True,
        "not_historical_full_2025":"2025 paired dataset stores winner only; cannot identify 2nd/3rd popularity",
        "source_files":[str(p.relative_to(ROOT)) for p in SOURCES],
        "sources_sha256":{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in SOURCES},
        "overall":stats(rows),"by_condition":groupby,
        "third_place_popularity_counts":dict(sorted(third_pops.items())),
        "outside_top3_popularity_counts_across_podium":dict(sorted(all_outside_pops.items())),
        "races":rows}
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    lines=["# 4番人気以下の3着以内・3着穴共通点｜JRA公式結果実測","",
       "**2026/10/31・11/1 東京・京都の48レースのうち、JRA公式結果から全馬人気順を取得できたレースのみ。人気は確定後・事後情報。**",
       f"公式結果 {len(sources)}R、全出走馬順位+人気照合 {len(rows)}R、除外 {len(failures)}R。","",
       f"4番人気以下が1頭以上3着以内：{result['overall']['any_outsider_top3_count']}/{len(rows)} ({result['overall']['any_outsider_top3_rate']:.1%})。",
       f"3着馬が4番人気以下：{result['overall']['third_outsider_count']}/{len(rows)} ({result['overall']['third_outsider_rate']:.1%})。",""]
    labels=[("開催日","date"),("競馬場","track"),("頭数","field_size"),("芝／ダート","surface"),("1番人気の勝敗","favorite_won")]
    for title,key in labels:
        lines+=["## "+title,"","|条件|レース数|4番人気以下が3着以内|4番人気以下が3着|",
               "|---|---:|---:|---:|"]
        for name,s in groupby[key].items():
            lines.append(f"|{name}|{s['n']}|{s['any_outsider_top3_count']}/{s['n']} ({s['any_outsider_top3_rate']:.1%})|{s['third_outsider_count']}/{s['n']} ({s['third_outsider_rate']:.1%})|")
        lines+=[""]
    lines+=["## 3着馬の最終人気分布","","|人気順位|3着回数|","|---|---:|"]
    for key,n in third_pops.items():lines.append(f"|{key}|{n}|")
    lines+=["","## 各レースの結果と人気順位","",
             "|日付|レース|頭数|1着人気|2着人気|3着人気|4番人気以下入着数|公式資料|",
             "|---|---|---:|---:|---:|---:|---:|---|"]
    for r in rows:
        ranks=r["top3_popularity"]
        lines.append(f"|{r['date']}|{r['race']}|{r['field_size']}|{ranks[0]}|{ranks[1]}|{ranks[2]}|{r['outsider_count_top3']}|[JRA公式]({r['official_result_url']})|")
    if failures:
        lines+=["","## データ不整合による除外",""]
        for item in failures:lines.append("- "+str(item))
    lines+=["","## 注意","",
            "- 観測研究のため原因ではなく条件付きの関連。競馬場・頭数・年齢・人気差等の交絡がある。",
            "- 最終人気を事前予測の入力に使わない。発走前に手動確認したオッズの人気順でのみ評価する。",
            "- 3着穴候補はモデルのp3と3着以内確率の両方を評価。後付けの最適係数は設定しない。",
            "- 2025年の既存モデルの396Rは勝ち馬のみのデータであり、2・3着人気の推測は禁止。",""]
    REPORT.write_text("\n".join(lines)+"\n")
    print(json.dumps({"verified":len(rows),"failed":len(failures),
        "overall":result["overall"],"conditions":groupby,"third_popularity":dict(third_pops),"errors":failures[:8]},ensure_ascii=False))

def guard(date,item):
    try:return extract(date,item)
    except Exception as exc:return {"date":date,"race":item["race"],"url":item["source_url"],"error":str(exc)[:260]}

if __name__=="__main__":main()
