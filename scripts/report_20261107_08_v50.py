"""Audit saved 2026-11-07/08 research probabilities and publish concise final tables."""
import json, math, hashlib
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"operations/predictions/2026-11-07/v50_weekend_research.json"
OUT=ROOT/"operations/predictions/2026-11-07/v50_weekend_final_report.md"
AUDIT=ROOT/"operations/predictions/2026-11-07/v50_weekend_audit.json"
GRADES={("2026-11-07","東京11R"),("2026-11-07","京都8R"),
        ("2026-11-08","東京11R"),("2026-11-08","京都11R")}

def report():
    source=SOURCE.read_bytes()
    data=json.loads(source)
    if data["full_cards_requested"]!=72:
        raise ValueError("Not all 72 races requested")
    statuses=Counter(r["status"] for r in data["races"])
    if len(data["races"])!=72:
        raise ValueError("Not all 72 races retained")
    if any(len([r for r in data["races"] if r["date"]==day])!=36
           for day in ("2026-11-07","2026-11-08")):
        raise ValueError("day coverage mismatch")
    audit=[]
    for r in data["races"]:
        if r["status"]!="research_probability_generated":
            continue
        horses=r["v50"]["horses"]
        p=[h["p1"] for h in horses]
        ps=[h["p2"] for h in horses]
        pt=[h["p3"] for h in horses]
        if len(horses)<3 or any(not math.isfinite(x) or x<=0 or x>=1 for x in p):
            raise ValueError("invalid probabilities: "+r["race"])
        if any(abs(sum(arr)-1)>1e-7 for arr in (p,ps,pt)):
            raise ValueError("probability mass mismatch: "+r["race"])
        if len({h["number"] for h in horses})!=len(horses):
            raise ValueError("duplicate runner: "+r["race"])
        audit.append({"date":r["date"],"race":r["race"],
                      "headcount":len(horses),"rider_matched":r["rider_matched"],
                      "source_quality":r["source_quality"],
                      "preoff_at_processing":r.get("preoff_at_processing")})
    lines=["# v50研究予測｜2026年11月7日・8日 JRA全72レース","",
           "**注意：v50標準版の正式予測ではなく、保存済み順位モデルによる通算成績代理特徴量を使用した研究予測です。確率は独立校正未済。**",
           "Aは過去の順位モデル由来の近似入力、v50は騎手残差を加え温度係数0.7で補正。B・C・Dは独立外部指数との同一出馬表照合ができていないため算出していません。",
           "障害戦3Rは平地用v50対象外。土曜日の発走済みレースについて事後計算した場合、発走前の正式予測とはみなしません。","",
           f"予測値生成：{statuses['research_probability_generated']}/72R、障害対象外：{statuses['unsupported_obstacle_model']}R。",
           f"全頭p1/p2/p3確率質量検査：{len(audit)}R合格。",
           f"一次データ内訳：{dict(Counter(a['source_quality'] for a in audit))}。",
           f"実行時点で発走前と確認できたもの：{sum(a['preoff_at_processing'] is True for a in audit)}R。",
           f"騎手残差照合：{sum(a['rider_matched'] for a in audit)}/{sum(a['headcount'] for a in audit)}頭。",""]
    for day in ("2026-11-07","2026-11-08"):
        lines += ["## "+day+"：全36レース","",
            "|レース|◎|1着モデル内確率|○|▲|データ確認|",
            "|---|---|---:|---|---|---|"]
        for r in data["races"]:
            if r["date"]!=day:continue
            if r["status"]!="research_probability_generated":
                lines.append(f"|{r['race']}|—|—|—|—|{r['status']}|")
                continue
            h=r["v50"]["horses"]
            lines.append(f"|{r['race']}|{h[0]['number']} {h[0]['name']}|{h[0]['p1']:.2%}|{h[1]['number']} {h[1]['name']}|{h[2]['number']} {h[2]['name']}|{r['source_quality']}|")
        chosen={(x["race"]) for x in data["top5_by_date"][day]}
        for date,race in GRADES:
            if date==day:chosen.add(race)
        lines+=["","## "+day+"：上位5レース＋重賞 詳細",""]
        for r in data["races"]:
            if r["date"]!=day or r["race"] not in chosen:continue
            lines += ["### "+r["race"],""]
            if r["status"]!="research_probability_generated":
                lines += ["障害戦／平地v50対象外。騎手補正後確率は算出しない。",""]
                continue
            h=r["v50"]["horses"]
            lines += [f"◎ {h[0]['number']} {h[0]['name']}（1着 {h[0]['p1']:.2%}）",
                      f"○ {h[1]['number']} {h[1]['name']}（1着 {h[1]['p1']:.2%}）",
                      f"▲ {h[2]['number']} {h[2]['name']}（1着 {h[2]['p1']:.2%}）",
                      f"☆ {h[3]['number']} {h[3]['name']}（1着 {h[3]['p1']:.2%}）",
                      "","|馬番・馬名|1着|2着|3着|3着以内（近似）|",
                      "|---|---:|---:|---:|---:|"]
            for item in h[:5]:
                lines.append(f"|{item['number']} {item['name']}|{item['p1']:.2%}|{item['p2']:.2%}|{item['p3']:.2%}|{item['p1']+item['p2']+item['p3']:.2%}|")
            lines += ["","最頻順序："+'→'.join(map(str,r["v50"]["ordered_top3"])),""]
            for key,title in (("single","単勝"),("quinella","馬連"),("trio","3連複")):
                tickets=r["v50"]["priority"][key]["tickets"]
                lines += [f"{title}：上位3組合せ（独立校正未済）","",
                          "|組合せ|モデル内確率|","|---|---:|"]
                for t in tickets[:3]:
                    lines.append(f"|{'-'.join(map(str,t['numbers']))}|{t['p']:.2%}|")
                lines.append("")
    OUT.write_text("\n".join(lines)+"\n")
    audit_result={"source_sha256":hashlib.sha256(source).hexdigest(),
                  "generated":len(audit),"requested":72,"statuses":dict(statuses),
                  "passes_probability_mass":len(audit),
                  "source_methods":dict(Counter(a["source_quality"] for a in audit)),
                  "preoff_confirmed":sum(a["preoff_at_processing"] is True for a in audit),
                  "rider_matches":sum(a["rider_matched"] for a in audit),
                  "total_horses":sum(a["headcount"] for a in audit)}
    AUDIT.write_text(json.dumps(audit_result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(audit_result,ensure_ascii=False))

if __name__=="__main__":report()
