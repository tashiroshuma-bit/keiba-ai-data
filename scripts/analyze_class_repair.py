"""Explain the fixed-cohort EV change; never use outcomes to select a model."""
import argparse
import collections
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'keiba_v48'))
from enriched_features import load_archive
from features import finish
from exceptional_results import ticket_hit
from repair_validation import ev_settlement


def analyze(db,results):
    _,fields,_=load_archive(db,allow_unlinked_fields=True)
    groups=collections.defaultdict(list)
    for row in fields:groups[row['race_id']].append(row)
    outputs=[]
    for lag in (2,7):
        root=Path(results)
        before={r['race_id']:r for r in json.loads((root/'replay'/f'repair_predictions_lag{lag}.json').read_text())}
        after={r['race_id']:r for r in json.loads((root/'class_repair'/f'repair_predictions_lag{lag}.json').read_text())}
        ids={r['race_id'] for r in json.loads((ROOT/'keiba_v48/reports/completion'/f'final_market_decisions_lag{lag}.json').read_text())}
        counts=collections.Counter();changes=[];summary={k:collections.Counter() for k in ('before','after')}
        for rid in sorted(ids):
            a=before[rid];b=after[rid]
            if a['horse_numbers']!=b['horse_numbers']:raise ValueError('field order changed')
            by={row['horse_number']:row for row in groups[rid]};rows=[by[n] for n in a['horse_numbers']]
            decisions={}
            for label,record in [('before',a),('after',b)]:
                decision=ev_settlement(rows,record['structural']);decisions[label]=decision
                if decision['horse_number'] is not None:
                    s=summary[label];s['bets']+=1;s['hits']+=decision['payout_yen']>0;s['payout_yen']+=decision['payout_yen']
                    s['selected_odds_100plus']+=decision['selected_odds']>=100
                    s['odds_sum']+=decision['selected_odds']
                for kind,n in [('wide',2),('trio',3)]:
                    chosen=sorted(range(len(rows)),key=lambda i:(-record['structural'][i],int(rows[i]['horse_number'])))[:n]
                    old=all(finish(rows[i]) is not None and finish(rows[i])<=3 for i in chosen)
                    counts[label+'_'+kind+'_actual_settlement_correction']+=old!=ticket_hit(rows,chosen,kind)
            if decisions['before']['horse_number']!=decisions['after']['horse_number']:
                counts['EV_selection_changed']+=1
                if decisions['before']['payout_yen']!=decisions['after']['payout_yen']:
                    changes.append(dict(race_id=rid,before=decisions['before'],after=decisions['after']))
        for label,s in summary.items():
            s['mean_selected_odds']=s.pop('odds_sum')/s['bets'];s['return_pct']=s['payout_yen']/s['bets']
        outputs.append(dict(lag_days=lag,cohort_races=len(ids),counts=dict(counts),summary={k:dict(v) for k,v in summary.items()},payout_changing_selections=changes,
                            role='post_hoc_diagnosis_only_not_model_selection'))
    return outputs


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--db',required=True);p.add_argument('--results',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    result=analyze(a.db,a.results);Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False))
