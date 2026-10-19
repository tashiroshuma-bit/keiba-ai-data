"""Virtual capital stress: no spending proceeds before source availability."""
import heapq
import math
from validation import equity_report
from features import timestamp


def risk_report(settlements,initial=100000):
    report=equity_report(settlements,initial)
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
    if not math.isfinite(initial) or initial<=0 or not math.isfinite(race_budget) or race_budget<0 or not 0<=race_fraction<=1 or not 0<=exposure_fraction<=1:
        raise ValueError('invalid virtual capital limits')
    if len({r['race_id'] for r in races})!=len(races):
        raise ValueError('duplicate capital replay race')
    cash=float(initial);queue=[];reserved=0.;serial=0;decisions=[];settled=[];max_exposure=0.
    peak=float(initial);maximum_drawdown=0.;equity_events=[]

    def release(limit):
        nonlocal cash,reserved,peak,maximum_drawdown
        while queue and queue[0][0]<=limit:
            at=queue[0][0]
            # Concurrent source observations form one event; arbitrary market
            # ordering must not manufacture an intrarace peak or drawdown.
            while queue and queue[0][0]==at:
                _,_,cost,payout=heapq.heappop(queue);reserved-=cost;cash+=payout
            equity=cash+reserved;peak=max(peak,equity)
            maximum_drawdown=max(maximum_drawdown,(peak-equity)/peak)
            equity_events.append(dict(observed_timestamp=at,equity_at_cost=equity))

    for r in sorted(races,key=lambda r:(timestamp(r['cutoff_timestamp']),r['race_id'])):
        at=timestamp(r['cutoff_timestamp']).timestamp()
        available=timestamp(r['result_available_at']).timestamp()
        if available<=at:
            raise ValueError('settlement availability must follow prediction cutoff')
        release(at)
        equity=cash+reserved
        cap=min(cash,race_budget,equity*race_fraction,max(0,equity*exposure_fraction-reserved))
        budget=int(cap//100)*100
        offers=[s for s in r['markets'] if s['stake_yen']>0]
        if any(s['stake_yen']!=100 for s in offers):
            raise ValueError('capital benchmark offers must be 100-yen units')
        chosen=offers[:budget//100];cost=100*len(chosen)
        decisions.append(dict(race_id=r['race_id'],stake_yen=cost,cash_before=cash,unsettled_cost_before=reserved,equity_before=equity))
        cash-=cost;reserved+=cost;max_exposure=max(max_exposure,reserved/equity if equity else 0)
        complete=all(s['fully_settled'] for s in chosen)
        settled.append(dict(race_id=r['race_id'],fully_settled=complete,stake_yen=cost,
                            payout_yen=sum(s['payout_yen'] for s in chosen) if complete else None))
        for s in chosen:
            if s['fully_settled']:
                if not math.isfinite(s['payout_yen']) or s['payout_yen']<0:
                    raise ValueError('invalid known payout')
                serial+=1;heapq.heappush(queue,(available,serial,100,s['payout_yen']))
        if cash<-.000001 or cost>cap+.000001:raise AssertionError('capital limit violation')
    release(float('inf'))
    report=risk_report(settled,initial)
    report['completed_race_order_drawdown']=report['maximum_drawdown']
    report['maximum_drawdown']=maximum_drawdown
    report.update(cash_after_known_settlements=cash,unresolved_reserved_cost=reserved,maximum_entry_exposure=max_exposure,
                  equity_at_cost_after_known_settlements=cash+reserved,equity_events=equity_events,
                  settlement_unit='race; partial races excluded from ROI',
                  drawdown_basis='source availability; unresolved stakes held at cost',
                  rule=dict(initial=initial,race_budget=race_budget,race_fraction=race_fraction,exposure_fraction=exposure_fraction),
                  role='probability_only_virtual_benchmark_not_executable_EV_strategy')
    return report,decisions
