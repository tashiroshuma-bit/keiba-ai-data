"""Actual statistical re-fit on 2025 archived preoff racewise horse predictors.

Conditional softmax residual model with a race-specific normalizer. Features
are strictly computed from frozen two model predictions, prior starts, number
of entrants and preoff confidence. The model is genuinely FIT via scipy L-BFGS
on 2025 training races, with regularization chosen on INTERNAL dates. The
outer 125-race chronological holdout is viewed once, never optimized against.

This is an experimental 2025 historical proxy, NOT canonical v50 re-training.
"""
import json,hashlib,math
from pathlib import Path
from collections import defaultdict
import numpy as np
from scipy.optimize import minimize
ROOT=Path(__file__).resolve().parents[1]
FROZEN=ROOT/"keiba_v48/reports/completion/paired_predictions_lag7.json"
RESULTS=ROOT/"reports/outsider_top3_history_2025.json"
OUT=ROOT/"reports/v50_horse_residual_retrained_2025.json"
MODEL=ROOT/"reports/v50_horse_residual_retrained_model_2025.json"
REPORT=ROOT/"reports/v50_horse_residual_retrained_2025.md"
FEATURES=("log_prior_vs_candidate","log_starts_centered","log_candidate_centered",
          "new_horse_indicator_centered","log_candidate_x_large_field",
          "log_prior_vs_candidate_x_low_history")
def features(r):
    pc=np.array(r["candidate"],dtype=float)
    pp=np.array(r["previous"],dtype=float)
    starts=np.array(r["history_starts"],dtype=float)
    if len(pc)!=len(pp) or len(pc)!=len(starts) or len(pc)<3:raise ValueError("bad lengths")
    if (pc<=0).any() or (pp<=0).any() or (starts<0).any() or not np.isfinite(pc).all():raise ValueError("invalid preoff features")
    if abs(pc.sum()-1)>1e-5 or abs(pp.sum()-1)>1e-5:raise ValueError("bad score sum")
    logp=np.log(pc);ratio=np.log(pp)-logp
    logstarts=np.log1p(starts)
    ratio_centered=ratio-ratio.mean()
    logp_centered=logp-logp.mean()
    logstarts_centered=logstarts-logstarts.mean()
    novice=(starts<=1).astype(float);novice=novice-novice.mean()
    larger=(len(pc)>=14)
    low_experience=(logstarts.mean()<math.log(3))
    X=np.column_stack([ratio_centered,logstarts_centered,logp_centered,novice,
      logp_centered*larger,ratio_centered*low_experience])
    return logp,X
def score(logits):
    v=logits-np.max(logits)
    w=np.exp(v);return w/w.sum()
def race(row,beta):
    l,x=row["design"]
    return score(l+x@beta)
def eval_rows(rows,beta,include_p3=False):
    logloss=brier=0.
    top1=top3=0
    results=[]
    for row in rows:
        p=race(row,beta)
        ranks=np.argsort(-p,kind="stable")
        winner=row["winner"]
        hit=bool(ranks[0]==winner)
        cap=bool(winner in ranks[:3])
        top1+=hit;top3+=cap
        logloss-=math.log(max(float(p[winner]),1e-12))
        brier+=sum((float(p[i])-(i==winner))**2 for i in range(len(p)))
        results.append({"race_id":row["race_id"],"date":row["date"],
           "winner_top1":hit,"winner_top3":cap,"winner_rank":int(np.where(ranks==winner)[0][0])+1,
           "winner_prob":float(p[winner]),"top1_prob":float(p[ranks[0]])})
    n=len(rows)
    return {"n":n,"top1":top1,"top1_rate":top1/n,"top3":top3,"top3_rate":top3/n,
      "logloss":logloss/n,"brier":brier/n,"races":results}
def fit(rows,lam):
    k=len(FEATURES)
    def loss(beta):
        ll=0.;grad=np.zeros(k)
        for row in rows:
            l,x=row["design"]
            logits=l+x@beta
            p=score(logits)
            y=row["winner"]
            ll-=math.log(max(float(p[y]),1e-30))
            grad+=x.T@p-x[y]
        ll=ll/len(rows)+.5*lam*(beta@beta)
        grad=grad/len(rows)+lam*beta
        return ll,grad
    res=minimize(loss,np.zeros(k),jac=True,method="L-BFGS-B",
                 options={"maxiter":500,"ftol":1e-12,"gtol":1e-9})
    if not res.success and np.linalg.norm(res.jac)>1e-5:
        raise ValueError("optimization failed: "+res.message)
    return np.asarray(res.x),{"success":bool(res.success),"nit":int(res.nit),
                              "objective":float(res.fun),"gradient_norm":float(np.linalg.norm(res.jac))}
def split_by_day(rows,fraction):
    days=sorted({r["date"] for r in rows})
    cutoff=days[max(0,int(len(days)*fraction)-1)]
    a=[r for r in rows if r["date"]<=cutoff]
    b=[r for r in rows if r["date"]>cutoff]
    assert a and b and max(r["date"] for r in a)<min(r["date"] for r in b)
    return a,b,cutoff
def main():
    history=json.loads(RESULTS.read_text())["races"]
    frozen={r["race_id"]:r for r in json.loads(FROZEN.read_text())}
    rows=[]
    for h in history:
        z=frozen.get(h["race_id"])
        if not z:continue
        if set(map(str,z["horse_numbers"]))!={str(k["number"]) for k in h["runners"]}:continue
        winning=str(h["top3_numbers"][0])
        ids=list(map(str,z["horse_numbers"]))
        design=features(z)
        rows.append({"race_id":h["race_id"],"date":h["date"],
                     "winner":ids.index(winning),"design":design})
    rows.sort(key=lambda r:(r["date"],r["race_id"]))
    if len(rows)!=351:raise ValueError("expected 351 matched race features")
    train,outer,outer_cut=split_by_day(rows,.7)
    fitpart,inner,inner_cut=split_by_day(train,.75)
    zero=np.zeros(len(FEATURES))
    tested=[]
    for lam in (.001,.005,.02,.1,.5,2.):
        beta,convergence=fit(fitpart,lam)
        val=eval_rows(inner,beta)
        tested.append({"lambda":lam,"beta":list(map(float,beta)),
                       "inner":{"n":val["n"],"top1":val["top1"],"top3":val["top3"],
                                "logloss":val["logloss"],"brier":val["brier"]},
                       "convergence":convergence})
    # Avoid ranking-only train tuning on the exterior test. Joint inner selection
    # favors hit count, then top3, then proper scoring rule.
    chosen=max(tested,key=lambda x:(x["inner"]["top1"],x["inner"]["top3"],
                                  -x["inner"]["logloss"],-x["lambda"]))
    b,final_fit=fit(train,chosen["lambda"])
    outer_base=eval_rows(outer,zero)
    outer_new=eval_rows(outer,b)
    outer_events=[{"race_id":a["race_id"],"old_hit":a["winner_top1"],
                   "new_hit":z["winner_top1"],"old_rank":a["winner_rank"],
                   "new_rank":z["winner_rank"]}
         for a,z in zip(outer_base["races"],outer_new["races"])]
    changes=[x for x in outer_events if x["old_hit"]!=x["new_hit"]]
    strict_improve=(outer_new["top1"]>outer_base["top1"]
      and outer_new["top3"]>=outer_base["top3"]
      and outer_new["logloss"]<=outer_base["logloss"]
      and outer_new["brier"]<=outer_base["brier"])
    model={"schema":"2025-historical-frozen-proxy-horse-residual-v1",
      "status":"trained_SHADOW_NOT_CANONICAL_V50","features":list(FEATURES),
      "coefficients":{k:float(v) for k,v in zip(FEATURES,b)},
      "lambda":chosen["lambda"],"fit_diagnostics":final_fit,
      "training_races":len(train),"training_cutoff_date":outer_cut,
      "sha256_2025_prediction_input":hashlib.sha256(FROZEN.read_bytes()).hexdigest(),
      "sha256_2025_results":hashlib.sha256(RESULTS.read_bytes()).hexdigest(),
      "external_canonical_v50_applicable":False,
      "no_final_odds_or_results_as_current_inputs":True}
    full={"schema":"historical-2025-horse-residual-retraining-v1",
      "training":{"n":len(train),"to_date":outer_cut},
      "internal":{"fit":len(fitpart),"validation":len(inner),"cutoff":inner_cut},
      "model_selection_grid":tested,
      "selected_lambda":chosen["lambda"],
      "trained_parameters":model["coefficients"],
      "outer_holdout":{"n":len(outer),"start":outer[0]["date"],
         "baseline":{k:v for k,v in outer_base.items() if k!="races"},
         "retrained":{k:v for k,v in outer_new.items() if k!="races"},
         "changed_1st_picks":changes},
      "strict_adoption_pass":strict_improve,
      "canonical_v50_modified":False,
      "limitations":["Historical 2025 predecessor prediction arrays not canonical v50.",
        "2025 historical sample of 351 may have selection bias and incomplete timestamp provenance.",
        "No current jockey/horse-id verified near-term history; those covariates cannot be trained here.",
        "Outer holdout not optimized after inspection.",
        "Even passing this test would not authorize promotion to canonical v50."]}
    MODEL.write_text(json.dumps(model,ensure_ascii=False,indent=2)+"\n")
    OUT.write_text(json.dumps(full,ensure_ascii=False,indent=2)+"\n")
    def pct(r,k):return f"{r[k]}/{r['n']} ({r[k+'_rate']:.1%})"
    L=["# v50研究：2025年保存済み実レースを使った馬の相対能力残差の実際の再学習","",
      "合計351R、学習226R、日付順の内部係数選択、後続の独立125R。",
      "**旧研究モデルの再学習であり、正式v50と同じ特徴量や騎手残差を備えた再学習ではない。**",
      f"学習で選択したL2正則化 {chosen['lambda']}。学習済み係数：{model['coefficients']}。","",
      "|区間|方式|本命的中|勝馬上位3捕捉|LogLoss|Brier|",
      "|---|---|---:|---:|---:|---:|"]
    for name,r in (("2025年後続125R","旧予測",outer_base),
                   ("2025年後続125R","再学習",outer_new)):
        L.append(f"|{name} | {r and ('旧予測' if r is outer_base else '再学習')}|{pct(r,'top1')}|{pct(r,'top3')}|{r['logloss']:.4f}|{r['brier']:.4f}|")
    L+=["",f"改善したレースと悪化したレースの指名逆転：{len(changes)}R。",
        f"複数指標の厳格な採用ゲート：{'PASS' if strict_improve else 'FAIL'}。",
        "前後の個別順位差と係数・内部検証の全記録はJSONに保存。","",
        "研究用モデルに正式v50の資格はない。canonical SQLiteと正しい事前馬・騎手履歴を連結した再学習には別工程が必要。",""]
    REPORT.write_text("\n".join(L)+"\n")
    print(json.dumps({"n":len(rows),"selected_lambda":chosen["lambda"],
       "outer_base":full["outer_holdout"]["baseline"],
       "outer_new":full["outer_holdout"]["retrained"],
       "strict_pass":strict_improve,"changes":len(changes)},ensure_ascii=False))
if __name__=="__main__":main()
