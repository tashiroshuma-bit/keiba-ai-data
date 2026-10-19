"""Virtual capital stress: no spending proceeds before source availability."""
import heapq
from validation import equity_report
from features import timestamp


def risk_report(settlements):
    report=equity_report(settlements,100000)
    paid=[s for s in settlements if s['fully_settled'] and s['stake_yen']>0]
    streak=longest=0
    for s in paid:
        streak=streak+1 if s['payout_yen']==0 else 0;longest=max(longest,streak)
    payouts=sorted([s['payout_yen'] for s in paid],reverse=True)
    stake=sum(s['stake_yen'] for s in paid);total=sum(payouts)
    report.update(bet_races=len(paid),longest_losing_streak=longest,
                  maximum_single_race_loss=max([max(0,s['stake_yen']-s['payout_yen']) for s in paid],default=0),
                  largest_payout_share=payouts[0]/total if total else None,
                  return_pct_without_largest_payout=100*(total-sum(payouts[:1]))/stake if stake else None,
                  return_pct_without_top3_payouts=100*(total-sum(payouts[:3]))/stake if stake else None)
    return report


def capital_replay(races,initial=100000,race_budget=5000,race_fraction=.02,exposure_fraction=.1):
    cash=float(initial);queue=[];reserved=0.;serial=0;decisions=[];settled=[];max_exposure=0.
    for r in sorted(races,key=lambda r:(timestamp(r['cutoff_timestamp']),r['race_id'])):
        at=timestamp(r['cutoff_timestamp']).timestamp()
        while queue and queue[0][0]<=at:
            _,_,cost,payout=heapq.heappop(queue);reserved-=cost;cash+=payout
        equity=cash+reserved
        cap=min(cash,race_budget,equity*race_fraction,max(0,equity*exposure_fraction-reserved))
        budget=int(cap//100)*100
        offers=[s for s in r['markets'] if s['stake_yen']>0]
        chosen=offers[:budget//100];cost=100*len(chosen)
        decisions.append(dict(race_id=r['race_id'],stake_yen=cost,cash_before=cash,unsettled_cost_before=reserved,equity_before=equity))
        cash-=cost;reserved+=cost;max_exposure=max(max_exposure,reserved/equity if equity else 0)
        for s in chosen:
            if s['fully_settled']:
                serial+=1;heapq.heappush(queue,(timestamp(r['result_available_at']).timestamp(),serial,100,s['payout_yen']))
            settled.append(s)
        if cash<-.000001 or cost>cap+.000001:raise AssertionError('capital limit violation')
    while queue:
        _,_,cost,payout=heapq.heappop(queue);reserved-=cost;cash+=payout
    report=risk_report(settled)
    report.update(cash_after_known_settlements=cash,unresolved_reserved_cost=reserved,maximum_entry_exposure=max_exposure,
                  rule=dict(initial=initial,race_budget=race_budget,race_fraction=race_fraction,exposure_fraction=exposure_fraction),
                  role='probability_only_virtual_benchmark_not_executable_EV_strategy')
    return report,decisions
