"""Post-race final-odds judgement axis. It is never a pre-off quote source."""
import math
from validation import equity_report, paired_report


def final_market_probabilities(odds):
    values = [float(o) for o in odds]
    if len(values) < 3 or any(not math.isfinite(o) or o < 1 for o in values):
        raise ValueError('complete finite final odds >= 1 required')
    weights = [1/o for o in values]
    return [w/sum(weights) for w in weights]


def judge_final_odds(rows, probabilities, min_expected_return=1.05):
    if len(rows) != len(probabilities) or not rows or not math.isfinite(min_expected_return) or min_expected_return < 1:
        raise ValueError('aligned full field and threshold >= 1 required')
    p = [float(v) for v in probabilities]
    if any(not math.isfinite(v) or not 0 <= v <= 1 for v in p) or abs(sum(p)-1) > 1e-8:
        raise ValueError('invalid win probabilities')
    numbers = [str(r['horse_number']) for r in rows]
    if len(set(numbers)) != len(numbers) or any(not n.isdigit() or int(n) < 1 for n in numbers):
        raise ValueError('unique positive horse numbers required')
    odds = [float(r['final_win_odds']) for r in rows]
    market = final_market_probabilities(odds)
    ranked = sorted(range(len(rows)), key=lambda i: (-p[i]*odds[i],int(numbers[i])))
    pick = ranked[0] if p[ranked[0]]*odds[ranked[0]] >= min_expected_return else None
    return dict(odds_basis='post_race_final',evaluation_role='hindsight_reference',
                actionable_before_off=False,threshold=min_expected_return,
                market_probabilities=market,
                value_rank=[numbers[i] for i in ranked],
                expected_returns=[p[i]*odds[i] for i in range(len(rows))],
                selected_index=pick,selected_horse_number=numbers[pick] if pick is not None else None)


def summarize_final_odds(records):
    """Records carry frozen model probabilities; final odds enter only this layer."""
    paired, settlements, details = [], [], []
    for r in records:
        judged = judge_final_odds(r['rows'],r['probabilities'])
        paired.append(dict(race_id=r['race_id'],baseline=judged['market_probabilities'],
                           candidate=r['probabilities'],winner_index=r['winner_index']))
        pick = judged['selected_index']
        payout = r['win_payout_100'] if pick == r['winner_index'] else 0
        settlements.append(dict(fully_settled=pick is None or payout is not None,
                                stake_yen=100 if pick is not None else 0,payout_yen=payout))
        details.append({'race_id':r['race_id'],**judged})
    report = paired_report(paired)
    report.update(odds_basis='post_race_final',evaluation_role='hindsight_reference_not_live_validation',
                  actionable_before_off=False,
                  post_race_value_rule='maximum p*final_odds >= 1.05; one 100-yen reference bet per race',
                  post_race_value_settlement=equity_report(settlements,100000))
    return report, details


def judge_combination_odds(horse_numbers, probabilities, quotes, kind, threshold=1.05):
    """Require full official final quotes; winning payouts cannot supply losing quotes."""
    import itertools
    if kind not in ('wide','trio') or not math.isfinite(threshold) or threshold<1:raise ValueError('invalid market')
    numbers=[str(n) for n in horse_numbers]
    if len(numbers)<3 or len(set(numbers))!=len(numbers) or any(not n.isdigit() or int(n)<1 or str(int(n))!=n for n in numbers):raise ValueError('invalid horse numbers')
    keys={','.join(c) for c in itertools.combinations(sorted(numbers,key=int),2 if kind=='wide' else 3)}
    prices={}
    for q in quotes:
        ns=list(map(str,q['horse_numbers']));key=','.join(sorted(ns,key=int));price=float(q['decimal_odds'])
        if key not in keys or key in prices or not math.isfinite(price) or price<1 or q.get('odds_basis')!='post_race_final' or not q.get('source_url','').startswith('https://'):raise ValueError('invalid final quote')
        prices[key]=price
    if set(prices)!=keys:return dict(status='blocked_missing_complete_final_market',ranked=[],actionable_before_off=False)
    if set(probabilities)!=keys or any(not math.isfinite(v) or not 0<=v<=1 for v in probabilities.values()):raise ValueError('invalid combination probabilities')
    ranked=sorted(keys,key=lambda k:(-probabilities[k]*prices[k],tuple(map(int,k.split(',')))))
    return dict(status='complete',ranked=[dict(horse_numbers=k.split(','),expected_return=probabilities[k]*prices[k]) for k in ranked],
                selected=ranked[0] if probabilities[ranked[0]]*prices[ranked[0]]>=threshold else None,actionable_before_off=False)
