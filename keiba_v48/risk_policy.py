"""Calibration-only risk-policy selection; keep non-approved candidates explicit."""
import collections
import math
import numpy as np
from features import finish,timestamp
from result_odds import final_market_probabilities


def policy_decision(race,structural,weight,cap,threshold=1.05):
    if not 0<=weight<=1 or threshold<1 or not math.isfinite(threshold):raise ValueError('invalid policy')
    rows=race['rows'];market=final_market_probabilities([r['final_win_odds'] for r in rows])
    if len(structural)!=len(rows) or abs(sum(structural)-1)>1e-8 or any(not math.isfinite(p) or not 0<=p<=1 for p in structural):raise ValueError('invalid structural probabilities')
    p=[weight*a+(1-weight)*b for a,b in zip(structural,market)]
    candidates=[i for i,r in enumerate(rows) if cap is None or r['final_win_odds']<=cap]
    order=sorted(candidates,key=lambda i:(-p[i]*rows[i]['final_win_odds'],int(rows[i]['horse_number'])))
    chosen=order[0] if order and p[order[0]]*rows[order[0]]['final_win_odds']>=threshold else None
    hit=chosen is not None and finish(rows[chosen])==1
    payout=rows[0]['win_payout_100'] if hit else 0
    return dict(fully_settled=not hit or payout is not None,stake_yen=100 if chosen is not None else 0,payout_yen=payout,
                horse_number=rows[chosen]['horse_number'] if chosen is not None else None,
                selected_odds=rows[chosen]['final_win_odds'] if chosen is not None else None),p


def calibrate_policy(races,structural,config):
    if not races or len(races)!=len(structural) or any(timestamp(r['off_timestamp']).year!=2024 for r in races):raise ValueError('risk policy uses 2024 only')
    dates=sorted({r['rows'][0]['race_date'] for r in races});ix={d:i for i,d in enumerate(dates)}
    rng=np.random.default_rng(48);sample=rng.integers(0,len(dates),size=(500,len(dates)))
    grid=[]
    for weight in config['mixture_structural_weights']:
        for cap in config['odds_caps']:
            stakes=np.zeros(len(dates));returns=np.zeros(len(dates));bets=0;pending=0
            for r,p in zip(races,structural):
                s,_=policy_decision(r,p,weight,cap,config['threshold']);pending+=not s['fully_settled']
                if s['fully_settled']:
                    d=ix[r['rows'][0]['race_date']];stakes[d]+=s['stake_yen'];returns[d]+=s['payout_yen'];bets+=s['stake_yen']>0
            total=stakes.sum();roi=100*returns.sum()/total if total else None
            a=stakes[sample].sum(axis=1);b=returns[sample].sum(axis=1);draws=100*b[a>0]/a[a>0]
            lower=float(np.quantile(draws,.025)) if len(draws) else None
            grid.append(dict(structural_weight=weight,odds_cap=cap,bets=int(bets),return_pct=roi,day_bootstrap_95pct_lower_return_pct=lower,pending=int(pending)))
    eligible=[g for g in grid if g['bets']>=config['minimum_calibration_bets'] and g['pending']==0]
    if not eligible:return dict(status='no_eligible_policy',approved=False,grid=grid,selected=None)
    best=max(eligible,key=lambda g:(g['day_bootstrap_95pct_lower_return_pct'],g['return_pct']))
    return dict(status='calibrated_research_policy',selected=best,approved=best['day_bootstrap_95pct_lower_return_pct']>100,grid=grid,
                selection_basis='2024 day-bootstrap lower ROI; minimum calibration bet count',live_eligible=False)
