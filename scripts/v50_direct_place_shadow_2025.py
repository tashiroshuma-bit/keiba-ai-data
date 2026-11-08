"""Train/evaluate coherent direct second/third placement shadow distributions.

Stage-1 probabilities stay fixed. Different temperature exponents for 2nd
and 3rd are trained on 2025 archive first 226 races and evaluated on later
125 races. They define a stage-wise PL joint distribution; no inconsistent
independent p1+p2+p3 sums or leaking final market positions.
"""
import json,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
H=ROOT/"reports/outsider_top3_history_2025.json"
P=ROOT/"keiba_v48/reports/completion/paired_predictions_lag7.json"
JSON=ROOT/"reports/v50_direct_place_p2_p3_2025.json"
MD=ROOT/"reports/v50_direct_place_p2_p3_2025.md"

def stage_marginals(p,gamma2,gamma3):
    if len(p)<3 or not all(x>0 and math.isfinite(x) for x in p) or abs(sum(p)-1)>1e-6:
        raise ValueError("first stage invalid probability")
    if gamma2<=0 or gamma3<=0:raise ValueError("invalid temperature exponents")
    n=len(p);w2=[x**gamma2 for x in p];w3=[x**gamma3 for x in p]
    s2=sum(w2);s3=sum(w3)
    second=[0.]*n;third=[0.]*n
    for i in range(n):
        den2=s2-w2[i]
        for j in range(n):
            if j==i:continue
            p12=p[i]*w2[j]/den2
            second[j]+=p12
            den3=s3-w3[i]-w3[j]
            for k in range(n):
                if k!=i and k!=j:
                    third[k]+=p12*w3[k]/den3
    if abs(sum(second)-1)>1e-6 or abs(sum(third)-1)>1e-6:
        raise ValueError("stage distributions not normalized")
    if any(p[i]+second[i]+third[i]>1+1e-6 for i in range(n)):
        raise ValueError("impossible total three-place probability")
    return second,third

def metric(pairs,g2,g3):
    n=len(pairs);ll2=ll3=br2=br3=0.0;second_top3=third_top3=0
    for q,r in pairs:
        p=q["candidate"]
        nums=[str(x) for x in q["horse_numbers"]]
        actual=[str(x) for x in r["top3_numbers"]]
        index={num:i for i,num in enumerate(nums)}
        p2,p3=stage_marginals(p,g2,g3)
        w2=index[actual[1]];w3=index[actual[2]]
        ll2-=math.log(max(p2[w2],1e-12));ll3-=math.log(max(p3[w3],1e-12))
        br2+=sum((v-int(i==w2))**2 for i,v in enumerate(p2))
        br3+=sum((v-int(i==w3))**2 for i,v in enumerate(p3))
        second_top3+=w2 in sorted(range(len(p)),key=lambda i:(-p2[i],nums[i]))[:3]
        third_top3+=w3 in sorted(range(len(p)),key=lambda i:(-p3[i],nums[i]))[:3]
    return {"n":n,"p2_logloss":ll2/n,"p3_logloss":ll3/n,
        "p2_brier":br2/n,"p3_brier":br3/n,
        "p2_3catch":second_top3,"p3_3catch":third_top3}

def main():
    archive={r["race_id"]:r for r in json.loads(P.read_text())}
    histories=json.loads(H.read_text())["races"]
    pairs=[]
    for r in histories:
        q=archive.get(r["race_id"])
        if q and {str(x) for x in q["horse_numbers"]}=={str(x["number"]) for x in r["runners"]}:
            pairs.append((q,r))
    pairs.sort(key=lambda x:(x[1]["date"],x[1]["race_id"]))
    if len(pairs)!=351:raise ValueError("frozen 351 missing")
    days=sorted({r["date"] for q,r in pairs});split=days[int(len(days)*.70)-1]
    train=[x for x in pairs if x[1]["date"]<=split]
    hold=[x for x in pairs if x[1]["date"]>split]
    baseline=metric(train,1.,1.)
    variants=[]
    for g2 in (.5,.75,1.,1.25,1.5):
        for g3 in (.5,.75,1.,1.25,1.5):
            v=metric(train,g2,g3)
            variants.append({"gamma2":g2,"gamma3":g3,"train":v})
    candidate=min(variants,key=lambda r:(r["train"]["p2_logloss"]+r["train"]["p3_logloss"],
                                        r["train"]["p3_brier"]))
    selected=metric(hold,candidate["gamma2"],candidate["gamma3"])
    base_hold=metric(hold,1.,1.)
    passes=(selected["p2_logloss"]<=base_hold["p2_logloss"] and
            selected["p3_logloss"]<base_hold["p3_logloss"] and
            selected["p3_brier"]<=base_hold["p3_brier"] and
            selected["p3_3catch"]>=base_hold["p3_3catch"])
    result={"status":"2025_POSITION_SPECIFIC_SHADOW_NOT_CANONICAL_V50",
      "train":{"count":len(train),"end":split,"base":baseline,"selected":candidate["train"]},
      "holdout":{"count":len(hold),"start":hold[0][1]["date"],
                 "base":base_hold,"selected":selected},
      "selected_parameters":{"gamma2":candidate["gamma2"],"gamma3":candidate["gamma3"]},
      "holdout_pass":passes,"future_v50_activated":False,
      "limitations":["2025 archived preoff candidate is not the canonical v50 model.",
                     "No final odds/finishing position used as current input.",
                     "Ranks are mutually exclusive and p1/2/3 coherent.",
                     "No independent v50 p2/p3 shadow replay established."]}
    JSON.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    L=["# v50研究：p2/p3専用の順位段階モデル・時系列検証","",
      "2025年351レース：学習226R、検証125R。1着確率p1は変更しない。",
      "2着・3着で別の温度係数を適用し、競合排除された正規化順位確率を計算。",
      f"学習のみで選んだ係数：{result['selected_parameters']}。",
      "|集合|方式|p2 Log Loss|p3 Log Loss|p3 Brier|2着上位3捕捉|3着上位3捕捉|",
      "|---|---|---:|---:|---:|---:|---:|"]
    for cohort in ("train","holdout"):
        for mode in ("base","selected"):
            v=result[cohort][mode]
            L.append(f"|{cohort}|{mode}|{v['p2_logloss']:.4f}|{v['p3_logloss']:.4f}|"
              f"{v['p3_brier']:.4f}|{v['p2_3catch']}/{v['n']}|{v['p3_3catch']}/{v['n']}|")
    L+=["",f"独立日程による研究候補のゲート：{'PASS' if passes else 'FAIL'}。",
      "PASSでもモデルの入力分布が正式v50と異なるため自動昇格しない。",""]
    MD.write_text("\n".join(L)+"\n")
    print(json.dumps({"selected":result["selected_parameters"],
      "holdout":result["holdout"],"passes":passes},ensure_ascii=False))
if __name__=="__main__":main()
