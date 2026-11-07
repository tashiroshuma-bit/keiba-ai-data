"""Publish mobile-friendly full drill-down for every Nov 7/8 A-D v50 race.

All scores are research model probabilities; do not present as calibrated
real-world hit rates. No synthetic missing B/C/D or jump scores.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"operations/predictions/2026-11-07/v50_weekend_abcd_reconnected.json"
BASE=ROOT/"operations/predictions/2026-11-07/v50_drilldown"
TRACKS=("東京","京都","福島")
DAYS=("2026-11-07","2026-11-08")
MODELS="ABCD"

def pct(x):
    return f"{x:.2%}"

def ticket_table(model,key,label):
    item=model["priority"][key]
    tickets=item.get("tickets") or []
    lines=[f"### {label}","",f"候補 {len(tickets)}点｜モデル内累積確率 {pct(item.get('cumulative',0))}","",
           "|番号|組合せ|個別確率|累積|","|---:|---|---:|---:|"]
    for i,t in enumerate(tickets,1):
        lines.append(f"|{i}|{'–'.join(str(v) for v in t['numbers'])}|{pct(t['p'])}|{pct(t['cumulative'])}|")
    if not tickets:lines.append("|—|算出なし|—|—|")
    return lines+[""]

def rider_provenance(record):
    result=[]
    if record.get("external_url"):
        result.append(f"外部指数：{record['external_url']}")
    if record.get("external_updated_at"):
        result.append(f"外部サイト掲載更新：{record['external_updated_at']}")
    result.append("外部指数の発走前保存が確認できたか："+("はい" if record.get("external_preoff_proven") else "未確認"))
    return result

def write_detail(r):
    day=r["date"]
    place=r["track"]
    n=r["race_number"]
    out=BASE/day/place/f"{n:02d}R.md"
    out.parent.mkdir(parents=True,exist_ok=True)
    models=r["models"]
    a=models["A"]["horses"]
    bymodel={label:{h["number"]:h for h in models[label]["horses"]} for label in MODELS}
    nums={h["number"] for h in a}
    for label in MODELS:
        field=models[label]["horses"]
        if len(field)!=len(nums) or {h["number"] for h in field}!=nums:
            raise ValueError(f"{day} {place}{n}: different runner lists")
        for attr in ("p1","p2","p3"):
            values=[h[attr] for h in field]
            if not all(math.isfinite(v) and 0<=v<=1 for v in values) or abs(sum(values)-1)>1e-7:
                raise ValueError(f"{day} {place}{n}: bad mass {label}/{attr}")
    lines=[f"# {day} {place}{n}R｜v50 A〜D詳細","",
           f"[開催日の一覧](../../{day}_INDEX.md) ｜ [全日一覧](../../INDEX.md)","",
           "**研究モデルの推定値です。発走前正式予測や検証済みの現実的中確率ではありません。**",
           "A：内部100%、B：内部75%＋外部25%、C：50%＋50%、D：内部25%＋外部75%。すべてv50騎手補正・温度係数0.7。",
           ""]
    for label in MODELS:
        h=models[label]["horses"]
        lines += [f"## モデル{label}","",
                  f"◎ {h[0]['number']} {h[0]['name']}：1着 {pct(h[0]['p1'])} ｜ "
                  + (" ○ "+str(h[1]['number'])+" "+h[1]['name'] if len(h)>1 else ""),
                  f"順序最頻：{' → '.join(str(i) for i in models[label]['ordered_top3'])}","",
                  "### 全出走馬の1・2・3着／3着以内確率","",
                  "|順位|馬番|馬名|1着|2着|3着|3着以内|",
                  "|---:|---:|---|---:|---:|---:|---:|"]
        for rank,hx in enumerate(h,1):
            top3=hx["p1"]+hx["p2"]+hx["p3"]
            lines.append(f"|{rank}|{hx['number']}|{hx['name']}|{pct(hx['p1'])}|{pct(hx['p2'])}|{pct(hx['p3'])}|{pct(top3)}|")
        lines+=[""]
        for k,label_name in (("single","単勝"),("quinella","馬連"),("trio","3連複")):
            lines+=ticket_table(models[label],k,label_name)
        lines+=["---",""]
    lines+=["## A〜D全頭1着確率の横並び比較","",
             "|馬番|馬名|A|B|C|D|",
             "|---:|---|---:|---:|---:|---:|"]
    for h in a:
        i=h["number"]
        lines.append(f"|{i}|{h['name']}|"+ "|".join(pct(bymodel[k][i]["p1"]) for k in MODELS)+"|")
    lines+=["","## データの取得根拠",""]+rider_provenance(r)+[
          "","外部指数は別モデルの参考入力であり、混合比率の独立的中率最適化は未実施。",
          "モデルの券種確率はPlackett–Luce近似に基づき、実際の馬券的中率を保証しません。",
          "直前の馬体重・馬場変化・最終オッズによる更新は、このレポートでは保証しません。",""]
    out.write_text("\n".join(lines)+"\n",encoding="utf-8")
    return out

def main():
    source_bytes=SRC.read_bytes()
    data=json.loads(source_bytes)
    if data.get("requested")!=72 or len(data["races"])!=72:
        raise ValueError("expected 72 race rows")
    if BASE.exists():
        raise FileExistsError("drilldown output already exists")
    success=defaultdict(dict);problems=defaultdict(dict);n=0
    for r in data["races"]:
        day,place,num=r["date"],r["track"],r["race_number"]
        if day not in DAYS or place not in TRACKS or not (1<=num<=12):
            raise ValueError("unknown race locator")
        key=(place,num)
        if key in success[day] or key in problems[day]:
            raise ValueError("duplicate race")
        if r["status"]=="abcd_reconnected":
            detail=write_detail(r)
            success[day][key]=detail
            n+=1
        else:
            problems[day][key]=r
    if any(len(success[day])+len(problems[day])!=36 for day in DAYS):
        raise ValueError("not all 36 race slots per day")
    if n!=data["reconnected"]:
        raise ValueError("generated count differs from source")
    for day in DAYS:
        lines=[f"# {day}｜v50 A〜D全36レース 詳細ナビ","",
           f"[2日間総合一覧](INDEX.md)","",
           f"詳細表示可能：{len(success[day])}/36R。","",
           "レース名を選ぶと、4モデルそれぞれの全頭1〜3着確率・単勝／馬連／3連複の全候補・A〜D横並び比較が見られます。","",
           "**モデル内研究確率であり独立校正未済。**",""]
        for place in TRACKS:
            lines += [f"## {place}","",
                     "|R|A〜D詳細|状態|","|---:|---|---|"]
            for num in range(1,13):
                key=(place,num)
                if key in success[day]:
                    detail=success[day][key]
                    relative=f"{day}/{place}/{num:02d}R.md"
                    lines.append(f"|{num}|[{place}{num}R：全頭確率・馬券別詳細]({relative})|4モデル計算済|")
                else:
                    r=problems[day][key]
                    reason=r.get("reason") or r["status"]
                    lines.append(f"|{num}|—|{reason}|")
            lines+=[""]
        (BASE/f"{day}_INDEX.md").write_text("\n".join(lines)+"\n")
    overview=["# 2026-11-07/08｜v50 A〜D予測 詳細ビュー","",
       f"全72レース：4モデル詳細 {n}レース、その他 {72-n}レース（障害3、外部指数照合拒否2）。","",
       f"- [11月7日（土）東京・京都・福島36R]({DAYS[0]}_INDEX.md)",
       f"- [11月8日（日）東京・京都・福島36R]({DAYS[1]}_INDEX.md)","",
       "各レースの詳細ページには **A/B/C/D別の全頭1〜3着確率、3着以内確率、単勝・馬連・3連複の各組合せ確率、全頭A〜D比較表** を掲載。","",
       "**注意：すべて研究計算であり、正式な発走前標準v50予測ではありません。**","",
       f"入力データSHA256: `{hashlib.sha256(source_bytes).hexdigest()}`",""]
    (BASE/"INDEX.md").write_text("\n".join(overview)+"\n")
    result={"created":n,"missing":72-n,"days":{day:len(success[day]) for day in DAYS},
            "source_sha256":hashlib.sha256(source_bytes).hexdigest(),
            "date_index_paths":[str(BASE/f"{day}_INDEX.md") for day in DAYS]}
    (BASE/"manifest.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(result,ensure_ascii=False))

if __name__=="__main__":main()
