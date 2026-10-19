"""Reproduce the original EV deterioration on the exact saved reference cohort."""
import argparse
import collections
import json
import math
from pathlib import Path
import statistics
from enriched_features import load_archive
from result_odds import judge_final_odds
from validation import canonical


def diagnose(db_path,predictions_path,reference_path,output):
    fixed_ids={r['race_id'] for r in json.loads(Path(reference_path).read_text())}
    h,rows,a=load_archive(db_path);groups=collections.defaultdict(list)
    for r in rows:groups[r['race_id']].append(r)
    preds=json.loads(Path(predictions_path).read_text());preds=[p for p in preds if p['race_id'] in fixed_ids];result={};decisions={};buckets=[(1,5),(5,10),(10,20),(20,50),(50,100),(100,float('inf'))]
    for name in ('previous','candidate'):
     selected=[];bins=[]
     for low,high in buckets:
      n=actual=0;expected=0
      for p in preds:
       rs={r['horse_number']:r for r in groups[p['race_id']]}
       for num,prob in zip(p['horse_numbers'],p[name]):
        r=rs[num];o=r.get('final_win_odds')
        if o is not None and low<=o<high:n+=1;actual+=r['finish_position']==1;expected+=prob
      bins.append(dict(odds_from=low,odds_to=high if math.isfinite(high) else None,runners=n,predicted_wins=expected,observed_wins=actual))
     for p in preds:
      rs0={r['horse_number']:r for r in groups[p['race_id']]};rs=[rs0[n] for n in p['horse_numbers']]
      if not all(r.get('final_win_odds') is not None for r in rs):continue
      j=judge_final_odds(rs,p[name]);i=j['selected_index']
      if i is None:continue
      r=rs[i];selected.append(dict(race_id=p['race_id'],horse_number=r['horse_number'],odds=r['final_win_odds'],p=p[name][i],EV=p[name][i]*r['final_win_odds'],won=r['finish_position']==1,payout=r['win_payout_100'] if r['finish_position']==1 else 0,history_starts=p['history_starts'][i]))
     result[name]=dict(bets=len(selected),hit_count=sum(x['won'] for x in selected),mean_selected_odds=statistics.mean(x['odds'] for x in selected),median_selected_odds=statistics.median(x['odds'] for x in selected),selected_odds_50plus=sum(x['odds']>=50 for x in selected),selected_odds_100plus=sum(x['odds']>=100 for x in selected),mean_predicted_EV=statistics.mean(x['EV'] for x in selected),realized_return_pct=sum(x['payout'] for x in selected)/len(selected),odds_band_calibration=bins)
     decisions[name]=selected
    dest=Path(output);dest.mkdir(parents=True,exist_ok=True)
    (dest/'deterioration_diagnosis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    (dest/'original_EV_decisions.json').write_text(canonical(decisions))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--db',required=True);p.add_argument('--predictions',required=True);p.add_argument('--reference-cohort',required=True);p.add_argument('--output',required=True);a=p.parse_args();print(json.dumps(diagnose(a.db,a.predictions,a.reference_cohort,a.output),ensure_ascii=False),flush=True)
