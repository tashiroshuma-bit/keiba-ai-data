#!/usr/bin/env python3
"""Re-roll 2026-10-25 research shadow with LIVE external AI rank comparison.
This is a live *external signal* refresh, not a retraining or probability calibration.
"""
import datetime as dt
import json, re, sys, time
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from bs4 import BeautifulSoup

BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE/"scripts"))
from external_muryou_keiba_reference import snapshot, compare, JST
SRC=BASE/"reports/20261025_allrace_rank_shadow/all_races.json"
OUT=BASE/"reports/20261025_allrace_rank_shadow"
TARGET={"win":.40,"quinella":.25,"trio":.30}
TYPES={"win":"単勝","quinella":"馬連","trio":"3連複"}
HOST="https://muryou-keiba-ai.jp"

def get(url):
    req=Request(url,headers={"User-Agent":"Mozilla/5.0 (compatible; JRAResearchPreOff/1.0)"})
    with urlopen(req,timeout=25) as r:
        return r.read().decode("utf-8","replace")

def listing():
    html=get(HOST+"/predict/")
    soup=BeautifulSoup(html,"html.parser")
    found={}
    for a in soup.find_all("a",href=True):
        t=" ".join(a.get_text(" ",strip=True).split())
        m=re.search(r"(京都|東京|新潟)\s+10月25日\s+(\d{1,2})R\s+(\d{2}:\d{2})",t)
        if not m:continue
        url=urljoin(HOST,a["href"])
        if not url.startswith(HOST+"/predict/2026/"):continue
        found[(m.group(1),int(m.group(2)))]=(url,m.group(3))
    return found

def priority(r,typ):
    ts=r["tickets"][typ]["tickets"]
    chosen=[];total=0
    for t in ts:
        total+=t["p"]
        chosen.append({"numbers":t["numbers"],"p":t["p"],"cumulative":total})
        if total>=TARGET[typ]-1e-10:break
    return {"tickets":chosen,"total":total,"threshold":TARGET[typ],"met":total>=TARGET[typ]-1e-10}

def main():
    now=dt.datetime.now(JST)
    races=json.loads(SRC.read_text(encoding="utf-8"))["races"]
    refs=listing()
    ext={};failed=[]
    for key,(url,clock) in refs.items():
        off=dt.datetime.fromisoformat("2026-10-25T"+clock+":00+09:00")
        try:
            html=get(url)
            snap=snapshot(url,now,off,html)
            matched=[r for r in races if (r["track"],r["race"])==key]
            if not matched:continue
            race=matched[0]
            cmp=compare(snap,race["ranked"])
            # Strict horse-name/number check before trusting external ranking.
            local={int(h["number"]):h["name"] for h in race["field"]}
            if cmp["status"]=="COMPARED_INDEPENDENTLY":
                for h in snap["horses"]:
                    raw=re.sub(r"\s+","",h["horse_name_and_jockey_raw"])
                    name=re.sub(r"\s+","",local[h["horse_number"]])
                    if not raw.startswith(name):
                        cmp={"status":"HORSE_NAME_MISMATCH","horse_number":h["horse_number"],"local":name,"external_raw":raw}
                        break
            if cmp["status"]=="COMPARED_INDEPENDENTLY":
                ext_order=[h["horse_number"] for h in sorted(snap["horses"],key=lambda h:-h["index"])]
                ext_rank={n:i for i,n in enumerate(ext_order,1)}
                internal_rank={h["number"]:i for i,h in enumerate(race["ranked"],1)}
                combined=sorted(ext_order,key=lambda n:(internal_rank[n]+ext_rank[n],internal_rank[n]))
                cmp["consensus_rank_sum_top5"]=combined[:5]
                cmp["agreement_top1"]=internal_rank[ext_order[0]]==1
            ext[f"{key[0]}{key[1]}R"]={"snapshot":snap,"comparison":cmp}
            print("OK",key,cmp["status"],flush=True)
        except Exception as e:
            failed.append({"race":f"{key[0]}{key[1]}R","reason":str(e)})
            print("FAIL",key,str(e),flush=True)
        time.sleep(.2)
    chosen=json.loads(SRC.read_text(encoding="utf-8"))["top5"]
    selected=[next(r for r in races if r["track"]==x["track"] and r["race"]==x["race"]) for x in chosen]
    kik=next(r for r in races if r["track"]=="京都" and r["race"]==11)
    chosen_races=selected+[kik]
    result={
      "status":"RESEARCH_SHADOW_EXTERNAL_REROLL_NOT_RETRAINED_NOT_CALIBRATED",
      "captured_at":now.isoformat(),
      "external_races_available":len(refs),
      "external_races_matched":len(ext),
      "external_races_verified":sum(x["comparison"]["status"]=="COMPARED_INDEPENDENTLY" for x in ext.values()),
      "external_failed":failed,
      "external":ext,
      "top5":[{"track":r["track"],"race":r["race"]} for r in selected],
      "priority":{f"{r['track']}{r['race']}R":{k:priority(r,k) for k in TARGET} for r in chosen_races},
      "internal_prediction_sha_provenance":"reports/20261025_allrace_rank_shadow/all_races.json",
      "notes":"Internal win/quinella/trio probabilities unchanged from stored research shadow; external signal is a separate rank comparison. No automatic probability blending or production V43 inference."
    }
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/"external_reroll_20261024.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    def pct(p):return f"{100*p:.2f}%"
    def ids(nums):return "－".join(str(n) for n in nums)
    lines=["# 2026年10月25日 JRA予測｜外部AI参照・再ローリング版","",
      f"取得時刻（日本時間）: {now.isoformat()}",
      f"外部サイト：{HOST}/predict/  掲載レース数：{len(refs)}、内部モデルと照合：{len(ext)}、馬名・馬番照合成功：{result['external_races_verified']}、取得エラー：{len(failed)}","",
      "**研究用・暫定。** 今回は外部AIの発走前指数を新規取得し、内部モデルの保存済み予測と再照合した。**内部の学習済みモデルは再学習・再推論しておらず、単勝・馬連・3連複の確率も更新していない。** 外部AI指数を的中確率と誤認せず、確率への混合もしていない。","",
      "## 上位5レース＋菊花賞（外部AI比較）","",
      "| レース | 内部◎○▲ | 内部◎勝率 | 外部AI上位3 | 本命一致 | 順位合算上位3 |",
      "|---|---|---:|---|---|---|"]
    for r in chosen_races:
        key=f"{r['track']}{r['race']}R"
        c=ext.get(key,{}).get("comparison",{})
        snap=ext.get(key,{}).get("snapshot",{})
        ok=c.get("status")=="COMPARED_INDEPENDENTLY"
        ex=ids(c["external_top3"]) if ok else c.get("status","未取得")
        con=ids(c["consensus_rank_sum_top5"][:3]) if ok else "未評価"
        lines.append(f"| {key} | {ids([h['number'] for h in r['ranked'][:3]])} | {pct(r['ranked'][0]['p1'])} | {ex} | {'一致' if c.get('agreement_top1') else '不一致／未評価'} | {con} |")
    lines+=["","順位合算は内部順位＋外部順位の小さい順。**勝率ではなく、候補の再点検用の参考順位**。馬券の確率や優先点数には外部AIの重みを未適用。","",
      "## 券種別・半目標を超える最小点数","",
      "| レース | 単勝40% | 馬連25% | 3連複30% |",
      "|---|---:|---:|---:|"]
    for r in chosen_races:
        key=f"{r['track']}{r['race']}R";p=result["priority"][key]
        lines.append("| "+key+" | "+" | ".join(f"{len(p[k]['tickets'])}点（{pct(p[k]['total'])}）" for k in TARGET)+" |")
    lines+=["","## 優先買い目・個別確率・累積確率（全件）",""]
    for r in chosen_races:
        key=f"{r['track']}{r['race']}R"
        lines.append("### "+key);lines.append("")
        for typ in TARGET:
            obj=result["priority"][key][typ]
            lines+=["#### "+TYPES[typ]+f" {len(obj['tickets'])}点／累積{pct(obj['total'])}","",
              "| 順位 | 買い目 | 個別モデル推定確率 | 累積モデル推定確率 |",
              "|---:|---|---:|---:|"]
            for i,t in enumerate(obj["tickets"],1):
                lines.append(f"| {i} | {ids(t['numbers'])} | {pct(t['p'])} | {pct(t['cumulative'])} |")
            lines.append("")
    lines+=["## 取得できた外部AIの全レース比較","",
      "| レース | 外部AI上位3 | 内部上位3 | 本命一致 | 外部更新時刻 | 出典 |",
      "|---|---|---|---|---|---|"]
    for key,e in sorted(ext.items()):
        c=e["comparison"];s=e["snapshot"]
        ex=ids(c["external_top3"]) if c["status"]=="COMPARED_INDEPENDENTLY" else c["status"]
        internal=ids(c["internal_top3"]) if c["status"]=="COMPARED_INDEPENDENTLY" else "未照合"
        lines.append(f"| {key} | {ex} | {internal} | {'○' if c.get('agreement_top1') else '×／未照合'} | {s.get('page_updated_at','不明')} | [出典]({s['url']}) |")
    lines+=["","## 限界と翌日更新","",
      "- 今回の外部参照は前日取得の独立比較。内部確率は学習時特徴量と一致しない代理特徴量に基づく**未校正の研究値**であり、実際の的中率ではない。",
      "- 当日の馬場・馬体重・出走取消・騎手変更・直前オッズは未反映。レース当日の別入力を受けた時点で更新する。",
      "- 菊花賞のような多数点は購入推奨ではない。実馬券購入はしない。",
      "- 外部サイトは当日朝にも更新され得る。取得時点の指数・順位と発走前タイムスタンプを保持し、結果情報を予測に混入させない。",
      "- 元の内部モデルと全券種確率は `all_races.json` の保存値を参照。正式V43の再推論とは異なる。",""]
    (OUT/"report_external_reroll_20261024.md").write_text("\n".join(lines),encoding="utf-8")
    print(json.dumps({"status":result["status"],"matched":len(ext),"verified":result["external_races_verified"],"failed":len(failed)},ensure_ascii=False))
    if result["external_races_verified"]<6:
        raise RuntimeError("Less than six priority races independently verified")

if __name__=="__main__":main()
