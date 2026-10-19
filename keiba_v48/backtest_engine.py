"""Leakage-resistant historical race evaluation. Input: race-level pre-off runner CSV.
No fabricated odds or historical predictions. Python standard library only.
"""
import argparse,csv,json,math,collections,datetime
from pathlib import Path

REQUIRED={'race_id','race_date','horse_number','horse_name','finish_position','pre_off_odds','odds_timestamp','off_timestamp'}
def read_rows(path):
    with open(path,encoding='utf-8-sig',newline='') as f:
        r=csv.DictReader(f)
        missing=REQUIRED-set(r.fieldnames or [])
        if missing:raise ValueError(f'Missing columns: {sorted(missing)}')
        return list(r)
def parse_time(s):
    value=datetime.datetime.fromisoformat(s.replace('Z','+00:00'))
    if value.tzinfo is None:raise ValueError('timezone offset required')
    return value
def check_race(rows):
    if len(rows)<3:raise ValueError('Race has fewer than 3 runners')
    if len({r['horse_number'] for r in rows})!=len(rows):raise ValueError('Duplicate horse number')
    if len({r['race_id'] for r in rows})!=1:raise ValueError('Mixed race IDs')
    if any(not r['pre_off_odds'] or not r['odds_timestamp'] or not r['off_timestamp'] for r in rows):raise ValueError('Missing timestamped pre-off odds')
    if any(parse_time(r['odds_timestamp'])>parse_time(r['off_timestamp']) for r in rows):raise ValueError('Post-off odds forbidden')
    if any(not math.isfinite(float(r['pre_off_odds'])) or float(r['pre_off_odds'])<=1 for r in rows):raise ValueError('Invalid odds')
    ranks=[int(r['finish_position']) for r in rows]
    if len(set(ranks))!=len(ranks) or min(ranks)!=1:raise ValueError('Missing/duplicate finishing ranks; exclude dead heats and nonfinishers until separately supported')

def probabilities(rows, score_field=None,alpha=0.0):
    weights=[1/float(r['pre_off_odds']) for r in rows]
    if score_field and alpha:
        if any(not r.get(score_field) for r in rows):raise ValueError('Missing pre-off score')
        scores=[float(r[score_field]) for r in rows]
        center=sum(scores)/len(scores)
        weights=[w*math.exp(max(-40,min(40,alpha*(s-center)))) for w,s in zip(weights,scores)]
    z=sum(weights)
    return [w/z for w in weights]

def podium(p):
    n=len(p); rank=[[0.,0.,0.] for _ in p];pair=collections.defaultdict(float);triple=collections.defaultdict(float)
    remain_one=[math.fsum(p[a] for a in range(n) if a!=i) for i in range(n)]
    remain_two={(i,j):math.fsum(p[a] for a in range(n) if a not in (i,j)) for i in range(n) for j in range(n) if i!=j}
    for i in range(n):
        rank[i][0]=p[i]
        for j in range(n):
            if i==j:continue
            remaining=remain_one[i]
            pij=p[i]*p[j]/remaining if remaining else 0.;rank[j][1]+=pij
            for k in range(n):
                if k in (i,j):continue
                remaining_two=remain_two[i,j]
                pr=pij*p[k]/remaining_two if remaining_two else 0.;rank[k][2]+=pr
                for a,b in ((i,j),(i,k),(j,k)):pair[tuple(sorted((a,b)))]+=pr
                triple[tuple(sorted((i,j,k)))]+=pr
    return rank,pair,triple

def analyze(rows,score_field=None,alpha=0.0):
    check_race(rows)
    p=probabilities(rows,score_field,alpha)
    rank,pair,triple=podium(p)
    winner=next(i for i,r in enumerate(rows) if int(r['finish_position'])==1)
    pick=max(range(len(p)),key=lambda i:p[i])
    # Settled using winner's historical FINAL payout odds, never pre-off odds.
    final=rows[winner].get('final_win_odds','')
    payout=100*float(final) if pick==winner and final else (0 if pick!=winner else None)
    return {'race_id':rows[0]['race_id'],'race_date':rows[0]['race_date'],'n_runners':len(rows),'winner':rows[winner]['horse_number'],'top_pick':rows[pick]['horse_number'],'top_pick_hit':int(pick==winner),'log_loss':-math.log(max(p[winner],1e-12)),'brier':sum((v-(i==winner))**2 for i,v in enumerate(p))/len(p),'stake_yen':100,'payout_yen':payout,'p_win_sum':sum(p),'p_rank_sums':[sum(q[k] for q in rank) for k in range(3)],'pair_probability_sum':sum(pair.values()),'triple_probability_sum':sum(triple.values())}

def run(path,score_field=None,alpha=0.0):
    data=read_rows(path);groups=collections.defaultdict(list)
    for row in data:groups[row['race_id']].append(row)
    valid=[];excluded=[]
    for race_id,rows in sorted(groups.items()):
        try:valid.append(analyze(rows,score_field,alpha))
        except Exception as e:excluded.append({'race_id':race_id,'reason':str(e)})
    paid=[r for r in valid if r['payout_yen'] is not None]
    return {'model':'market_normalized' if not score_field or alpha==0 else 'market_plus_score_UNFITTED','race_count':len(valid),'excluded':excluded,'top_pick_accuracy':sum(r['top_pick_hit'] for r in valid)/len(valid) if valid else None,'mean_log_loss':sum(r['log_loss'] for r in valid)/len(valid) if valid else None,'mean_brier':sum(r['brier'] for r in valid)/len(valid) if valid else None,'settled_races':len(paid),'return_pct':100*sum(r['payout_yen'] for r in paid)/sum(r['stake_yen'] for r in paid) if paid else None,'races':valid}
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('csv');ap.add_argument('--score-field');ap.add_argument('--alpha',type=float,default=0);ap.add_argument('--output');a=ap.parse_args()
    out=run(a.csv,a.score_field,a.alpha)
    s=json.dumps(out,ensure_ascii=False,indent=2)
    if a.output:Path(a.output).write_text(s,encoding='utf-8')
    print(s)
