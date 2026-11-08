"""Evaluate historical major-upset rarity and a preoff-only conditional gate.

Data: archived 351 2025 races with all three final ranks / popularity, joined
to frozen historical candidate/previous probabilities. All labels post-race,
all predictor features archived pre-race except unavoidable sampling caveats.
Strict chronological 70/30 partition, threshold chosen TRAIN only. NO PROMOTION
unless validation holdout has at least 3 rare examples and 2x lift with
<=15% flagged races and no severe false-negative masking.
"""
from __future__ import annotations
import json,math,hashlib,datetime as dt
from collections import defaultdict,Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
HISTORY=ROOT/"reports/outsider_top3_history_2025.json"
PRED=ROOT/"keiba_v48/reports/completion/paired_predictions_lag7.json"
SUNDAY=ROOT/"operations/results/2026-11-08/v50_abcd_settlement.json"
JSON=ROOT/"reports/v50_rare_upset_gate_2025.json"
MD=ROOT/"reports/v50_rare_upset_gate_2025.md"
POLICY=ROOT/"operations/prediction_policy/v50_rare_upset_gate_research.json"

def entropy(p):
    q=[x for x in p if x>0];return -sum(x*math.log(x) for x in q)/math.log(len(p))
def features(p,starts,field):
    assert len(p)==field and len(starts)==field and abs(sum(p)-1)<1e-5
    order=sorted(p,reverse=True)
    return {"field_size":field,"candidate_max_p1":order[0],
      "candidate_gap_1_2":order[0]-order[1],
      "candidate_entropy":entropy(p),
      "candidate_top3_share":sum(order[:3]),
      "fraction_start_le1":sum(x<=1 for x in starts)/field,
      "mean_prior_starts":sum(starts)/field}
def define_event(ranks):
    if len(ranks)!=3:return False
    # A Tokyo11R-style unprecedented collective upset, not ordinary
    # one-outsider win: three podium horses at market popularity >=7.
    return min(ranks)>=7
def define_extended(ranks):
    return ranks[0]>=10 and sum(n>=7 for n in ranks)>=2
def condition(row,rule):
    return (row["features"]["field_size"]>=rule["min_field"] and
      row["features"]["candidate_max_p1"]<=rule["max_top1"] and
      row["features"]["candidate_gap_1_2"]<=rule["max_gap"] and
      row["features"]["candidate_entropy"]>=rule["min_entropy"])
def results(rows, rule):
    chosen=[r for r in rows if condition(r,rule)]
    positives=sum(r["extreme_upset"] for r in rows)
    hits=sum(r["extreme_upset"] for r in chosen)
    p=len(chosen)
    return {"races":len(rows),"extreme_upsets":positives,"flagged":p,
      "flag_rate":p/len(rows) if rows else None,
      "extreme_hits":hits,
      "precision":hits/p if p else None,
      "recall":hits/positives if positives else None,
      "base_rate":positives/len(rows) if rows else None,
      "lift_vs_base":(hits/p)/(positives/len(rows)) if p and positives else None,
      "false_positive":p-hits}
def main():
    hist=json.loads(HISTORY.read_text())
    preds=json.loads(PRED.read_text())
    idx={r["race_id"]:r for r in preds}
    rows=[];errors=[]
    for r in hist["races"]:
        id=r["race_id"];q=idx.get(id)
        if not q:errors.append([id,"missing frozen forecasts"]);continue
        nums=[str(x) for x in q["horse_numbers"]]
        if set(nums)!={str(x["number"]) for x in r["runners"]}:
            errors.append([id,"frozen horse field conflict"]);continue
        try:features0=features(q["candidate"],q["history_starts"],len(nums))
        except (KeyError,TypeError,ValueError,AssertionError) as e:
            errors.append([id,"invalid model features "+str(e)]);continue
        ranks=r["top3_popularity"]
        rows.append({"race_id":id,"date":r["date"],"venue":r["venue"],
             "top3_final_popularity":ranks,"extreme_upset":define_event(ranks),
             "extended_upset":define_extended(ranks),
             "nonfavorite_winner":ranks[0]>=4,
             "features":features0})
    rows.sort(key=lambda x:(x["date"],x["race_id"]))
    if len(rows)<320:raise RuntimeError("matched 2025 races below expected scope")
    # Whole-day split: do not let same-day outcome information leak into validation.
    days=sorted({r["date"] for r in rows})
    split=days[max(0,int(len(days)*.70)-1)]
    train=[r for r in rows if r["date"]<=split]
    test=[r for r in rows if r["date"]>split]
    assert train and test and max(x["date"] for x in train)<min(x["date"] for x in test)
    grid=[{"min_field":f,"max_top1":p,"max_gap":g,"min_entropy":e}
          for f in (12,14,16)
          for p in (.12,.16,.20,.25)
          for g in (.01,.02,.04,.08)
          for e in (.88,.93,.97)]
    # Empty/near-empty event cannot teach a rare event signal.
    scored=[]
    for rule in grid:
        st=results(train,rule)
        if st["flagged"]<8 or st["flag_rate"]>.15 or st["extreme_hits"]<2:
            continue
        scored.append((st["precision"],st["recall"],-st["flag_rate"],rule,st))
    scored.sort(key=lambda x:(x[0],x[1],x[2]),reverse=True)
    chosen=scored[0][3] if scored else None
    train_ev=results(train,chosen) if chosen else None
    test_ev=results(test,chosen) if chosen else None
    validated=bool(chosen and train_ev["extreme_hits"]>=2 and
         test_ev["extreme_upsets"]>=3 and test_ev["extreme_hits"]>=2 and
         test_ev["flag_rate"]<=.15 and test_ev["lift_vs_base"] is not None and
         test_ev["lift_vs_base"]>=2)
    # Prospective trigger always gated behind independent validation.
    policy={"version":"v50","status":"research_only",
       "activation":"CONDITIONAL_ONLY_IF_CHRONOLOGICALLY_VALIDATED",
       "definition":{"extreme":"all 1st 2nd 3rd final popularity 7th-or-lower",
                     "extended":"winner 10th-or-lower and at least two podium 7th-or-lower"},
       "preoff_features":["field_size","candidate_max_p1",
         "candidate_gap_1_2","candidate_entropy"],
       "candidate_rule":chosen,"enabled":validated,
       "candidate_train":train_ev,"candidate_holdout":test_ev,
       "no_conditional_reweighting_without_proven_oos_gain":True,
       "fallback":"canonical_v50_unchanged",
       "never_use_postrace_popularity_in_preoff_features":True,
       "sources":["reports/outsider_top3_history_2025.json",
                  "keiba_v48/reports/completion/paired_predictions_lag7.json"]}
    POLICY.write_text(json.dumps(policy,ensure_ascii=False,indent=2)+"\n")
    overall=results(rows,{"min_field":0,"max_top1":1.,"max_gap":1.,"min_entropy":0})
    sunday=json.loads(SUNDAY.read_text())
    sunday_eval=[r for r in sunday["races"] if r["status"]=="evaluated"]
    sunday_ext=[r for r in sunday_eval if define_event(r["final_popularity"])]
    sunday_extended=[r for r in sunday_eval if define_extended(r["final_popularity"])]
    report={"schema":"v50-rare-upset-2025-historical-v1",
       "definition":policy["definition"],
       "matched_2025":len(rows),"skipped":errors,"full":overall,
       "extended_2025":sum(r["extended_upset"] for r in rows),
       "extreme_by_venue":dict(Counter(r["venue"] for r in rows if r["extreme_upset"])),
       "extreme_by_field":dict(Counter(str(r["features"]["field_size"]) for r in rows if r["extreme_upset"])),
       "extreme_race_ids":[r["race_id"] for r in rows if r["extreme_upset"]],
       "field_size":{str(k):{"n":len(v),"events":sum(x["extreme_upset"] for x in v)}
          for k,v in sorted(((n,[r for r in rows if r["features"]["field_size"]==n])
                             for n in sorted({r["features"]["field_size"] for r in rows})))},
       "train": {"n":len(train),"extreme":sum(r["extreme_upset"] for r in train),
                 "last_date":train[-1]["date"]},
       "holdout":{"n":len(test),"extreme":sum(r["extreme_upset"] for r in test),
                  "first_date":test[0]["date"]},
       "selected_train_rule":chosen,"train_metrics":train_ev,"holdout_metrics":test_ev,
       "rule_deployable":validated,
       "2026_11_08":{"n":len(sunday_eval),"extreme_count":len(sunday_ext),
                     "extreme_races":[r["race"] for r in sunday_ext],
                     "extended_count":len(sunday_extended),
                     "extended_races":[r["race"] for r in sunday_extended]},
       "cautions":["Final popularity determines historical labels only; never model input.",
         "2025 frozen candidate score is a different model from canonical v50; transferable rule not proven.",
         "Sample is a selected 351-race cohort, NOT all JRA 2025 races.",
         "Extremely rare events have unstable confidence intervals; no model activation absent sufficient holdout support."]}
    JSON.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    lines=["# 2025年過去351レース｜東京11R級・超大波乱の頻度と予兆分析","",
      "**超大波乱＝3着以内の全3頭が最終7番人気以下**。単に4番人気以下が勝ったレースと混同しない。",
      "定義は11月8日を確認した後の探索的な研究定義。2025年検証への転用は事後的であり将来性能を保証しない。",
      f"2025実データ照合 {len(rows)}/351レース、超大波乱 {overall['extreme_upsets']}R ({overall['base_rate']:.2%})。",
      f"拡張型（10番人気以下勝利、かつ7番人気以下2頭以上が入着）{report['extended_2025']}R。",
      f"2026-11-08平地34Rで超大波乱 {len(sunday_ext)}R（{', '.join(report['2026_11_08']['extreme_races']) or 'なし'}）。",
      f"開催日で分割：学習{len(train)}R（{train[-1]['date']}まで）、検証{len(test)}R（{test[0]['date']}以降）。","",
      "## 2025年・超大波乱が起きた開催場","",
      "|場所|レース数|","|---|---:|"]
    for k,v in report["extreme_by_venue"].items():lines.append(f"|{k}|{v}|")
    lines+=["","## 予測前に使える候補条件の検証","",
      "- 出走頭数",
      "- 当時保存された予測の1着トップ確率",
      "- 予測1位と2位の確率差",
      "- 予測確率の正規化エントロピー",
      "",
      f"候補ルール：{chosen if chosen else '学習データでもサポート要件を満たすルールなし'}。",
      f"学習結果：{train_ev if train_ev else '該当なし'}。",
      f"時系列未学習データ：{test_ev if test_ev else '該当なし'}。",
      f"独立検証を満たし適用可：**{validated}**。",
      "満たさない場合は必ず**通常v50を維持**し、波乱補正しない。大波乱の的中を約束するモードは作らない。",
      "",
      "## 制約・解釈",""]+["- "+x for x in report["cautions"]]
    MD.write_text("\n".join(lines)+"\n")
    print(json.dumps({"matched":len(rows),"extreme_2025":overall["extreme_upsets"],
      "extended_2025":report["extended_2025"],
      "train":report["train"],"holdout":report["holdout"],
      "selected_rule":chosen,"training":train_ev,"validation":test_ev,
      "enabled":validated,"sunday":report["2026_11_08"]},ensure_ascii=False))

if __name__=="__main__":main()
