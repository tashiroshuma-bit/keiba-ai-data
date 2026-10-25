"""Reconcile immutable research forecasts. No deployment changes or purchases."""
import csv
import hashlib
import itertools
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'reports/weekend_20261024_25'


def normalized(weights, exponent=1.0, nonstarters=()):
    if not math.isfinite(exponent) or exponent <= 0:
        raise ValueError('positive exponent required')
    kept = {n:p for n,p in weights.items() if n not in nonstarters}
    if not kept or any(not math.isfinite(p) or p <= 0 for p in kept.values()):
        raise ValueError('finite positive weights required')
    logs = {n:math.log(p)*exponent for n,p in kept.items()}
    peak = max(logs.values())
    scaled = {n:math.exp(v-peak) for n,v in logs.items()}
    total = sum(scaled.values())
    return {n:p/total for n,p in scaled.items()}


def rank_distribution(weights):
    """Recompute ALL placing and joint probabilities after a scratch/correction."""
    p = normalized(weights)
    if len(p) < 3:
        raise ValueError('at least three runners required')
    marginal = {n:[v,0.,0.] for n,v in p.items()}
    triples = {}
    for a,b,c in itertools.permutations(p,3):
        q = p[a] * p[b]/(1-p[a]) * p[c]/(1-p[a]-p[b])
        triples[a,b,c] = q
        marginal[b][1] += q
        marginal[c][2] += q
    return marginal, triples


def wide_union(triples, pairs):
    pairs = {frozenset(pair) for pair in pairs}
    return sum(p for triple,p in triples.items() if any(pair <= set(triple) for pair in pairs))


def validate_revision(parent, child):
    """A later timestamp alone must not silently choose a different branch."""
    if child.get('parent_prediction_sha256') != parent['prediction_sha256']:
        raise ValueError('prediction parent mismatch')
    if child.get('variant') != parent['variant'] and not child.get('variant_switch_reason'):
        raise ValueError('explicit branch-switch reason required')


def settle(tickets, payouts, nonstarters=()):
    paid = refunded = hits = 0
    for t in tickets:
        nums = t['numbers']
        if set(nums) & set(nonstarters):
            refunded += 100
        else:
            value = payouts.get('-'.join(map(str, sorted(nums))),0)
            paid += value
            hits += bool(value)
    return dict(points=len(tickets), hypothetical_stake_yen=100*len(tickets),
                hypothetical_payout_yen=paid, hypothetical_refund_yen=refunded, hit_tickets=hits,
                hit_race=int(hits>0))


def evaluate(weights, result):
    p = normalized(weights)  # only removes stored rounding error, keeps frozen nonstarters
    order = sorted(p, key=lambda n:(-p[n], n))
    top = result['top3']
    winners = [n for rank,n in top if rank==1]
    if len(winners)!=1:
        raise ValueError('first-place tie needs separate scoring protocol')
    winner = winners[0]
    valid_orders = [tuple(map(int,k.split('-'))) for k in result['payouts']['trifecta']]
    valid_sets = [set(map(int,k.split('-'))) for k in result['payouts']['trio']]
    actual = {n for _,n in top}
    return dict(top1=order[0], top3=order[:3], top1_hit=int(order[0]==winner),
        winner_in_top3=int(winner in order[:3]), top3_capture_count=len(set(order[:3])&actual),
        ordered_hit=int(tuple(order[:3]) in valid_orders), unordered_hit=int(set(order[:3]) in valid_sets),
        top1_probability=p[order[0]], winner_probability=p.get(winner,0),
        log_loss=-math.log(max(p.get(winner,0),1e-15)),
        brier_sum=sum((v-int(n==winner))**2 for n,v in p.items()),
        top1_tied=sum(abs(v-p[order[0]])<1e-9 for v in p.values())>1,
        uniform=max(p.values())-min(p.values())<1e-9)


def aggregate(rows):
    n=len(rows)
    keys=('top1_hit','winner_in_top3','ordered_hit','unordered_hit','top3_capture_count','log_loss','brier_sum','top1_probability')
    out={'races':n, **{k:sum(r[k] for r in rows)/n for k in keys},
         'top1_tied_races':sum(r['top1_tied'] for r in rows),'uniform_races':sum(r['uniform'] for r in rows)}
    out['calibration_bins']=[]
    for lo,hi in [(0,.1),(.1,.2),(.2,.3),(.3,.5),(.5,1.00001)]:
        group=[r for r in rows if lo<=r['top1_probability']<hi]
        if group:
            out['calibration_bins'].append({'range':[lo,min(hi,1)],'races':len(group),
                'mean_forecast':sum(r['top1_probability'] for r in group)/len(group),
                'observed_hit_rate':sum(r['top1_hit'] for r in group)/len(group)})
    return out


def calibrate_diagnostic(races, results):
    """Exploratory venue-held-out diagnostic, NOT a 2024 selection or future test."""
    grid=[.5,.75,1.,1.25,1.5,2.,3.,4.]
    diagnostics={}
    for model in 'ABCD':
        eligible=[r for r in races if not results['20261025',r['race']]['nonstarters']]
        folds=[]; before=[]; after=[]
        def loss(r,e):
            weights={h['no']:h['p1'] for h in r['models'][model]['horses']}
            return evaluate(normalized(weights,e),results['20261025',r['race']])['log_loss']
        for venue in ('東京','京都','新潟'):
            train=[r for r in eligible if not r['race'].startswith(venue)]
            test=[r for r in eligible if r['race'].startswith(venue)]
            e=min(grid,key=lambda e:(sum(loss(r,e) for r in train),abs(e-1)))
            old=[loss(r,1) for r in test]; new=[loss(r,e) for r in test]
            before+=old;after+=new
            folds.append(dict(held_out_venue=venue,train_races=len(train),test_races=len(test),
                exponent=e,before_log_loss=sum(old)/len(old),after_log_loss=sum(new)/len(new)))
        full=min(grid,key=lambda e:(sum(loss(r,e) for r in eligible),abs(e-1)))
        diagnostics[model]=dict(races=len(eligible),folds=folds,
            crossfit_before_log_loss=sum(before)/len(before),crossfit_after_log_loss=sum(after)/len(after),
            exploratory_full_sample_exponent=full,
            deployment_exponent=1.0,decision='DO_NOT_PROMOTE_2026_OUTCOME_FIT',
            reason='One race day; retrospective venue folds are correlated. Fit on 2024 for adoption; rank order unchanged.')
    return diagnostics


def markdown_variant(path):
    """Read actually saved rounded Kikka tables; do not recreate missing tickets."""
    text=path.read_text()
    blocks=re.split(r'<details><summary>([ABCD])モデル[^\n]*\n',text)
    variants={}
    for i in range(1,len(blocks),2):
        model,block=blocks[i:i+2]
        horses=[]
        for m in re.finditer(r'^\|\s*(\d+) [^|]+\|[^|]+\|\s*([\d.]+)%\|',block,re.M):
            horses.append({'no':int(m[1]),'p1':float(m[2])/100})
        if not horses: continue
        markets={}
        for label,key in [('単勝','single'),('馬連','quinella'),('3連複','trio')]:
            match=re.search(r'### '+label+r' .*?\n(.*?)(?=\n### |</details>|\Z)',block,re.S)
            markets[key]=[{'numbers':list(map(int,m[1].split('-')))} for m in re.finditer(r'^\|([\d-]+)\|[\d.]+%\|',match[1],re.M)] if match else []
        variants[model]={'horses':horses,'priority':markets}
    return variants


def six_race_variants(path):
    text=path.read_text()
    races=re.split(r'<details><summary><strong>((?:東京|京都|新潟)\d+R)[^<]*</strong>[^\n]*\n',text)
    out=[]
    for i in range(1,len(races),2):
        race,body=races[i:i+2]
        models=re.split(r'<details><summary><strong>([ABCD])モデル</strong>[^\n]*\n',body)
        for j in range(1,len(models),2):
            model,block=models[j:j+2]
            horses=[{'no':int(m[1]),'p1':float(m[2])/100} for m in re.finditer(
                r'^\|\s*(\d+) [^|]+\|[^|]+\|\s*([\d.]+)%\s*\|',block,re.M)]
            priority={}
            for label,key in [('単勝','single'),('馬連','quinella'),('3連複','trio')]:
                m=re.search(r'\*\*'+label+r'：.*?\n(.*?)(?=\n\*\*|</details>|\Z)',block,re.S)
                priority[key]=[{'numbers':list(map(int,x[1].replace('－','-').split('-')))} for x in re.finditer(
                    r'^\|\s*\d+\s*\|\s*([\d－-]+)\s*\|\s*[\d.]+%',m[1],re.M)] if m else []
            assert horses and all(priority.values()),(race,model)
            out.append({'race':race,'model':model,'horses':horses,'priority':priority})
    assert len(out)==24
    return out


def main():
    OUT.mkdir(exist_ok=True)
    observations=json.loads((ROOT/'operations/results/2026-10-25/weekend_observations.json').read_text())
    results={(r['date'],r['race']):r for r in observations['races']}
    freeze=json.loads((ROOT/'operations/predictions/2026-10-25/freeze_20261025T080138+0900.json').read_text())
    for item in freeze['immutable_payloads']:
        if 'sha256' in item:
            assert hashlib.sha256((ROOT/item['path']).read_bytes()).hexdigest()==item['sha256'], item['path']
    forecasts=json.loads((ROOT/'reports/20261025_four_model_all_probabilities.json').read_text())['races']
    fallback=json.loads((ROOT/'reports/20261024_manual_fallback/predictions.json').read_text())['races']
    rows=[]; settlements=[]; summaries={}
    for model in 'ABCD':
        group=[]
        for r in forecasts:
            actual=results['20261025',r['race']]
            weights={h['no']:h['p1'] for h in r['models'][model]['horses']}
            row=dict(date='20261025',race=r['race'],model=model,**evaluate(weights,actual))
            rows.append(row);group.append(row)
            for market,data in r['models'][model]['priority'].items():
                settlements.append(dict(date='20261025',race=r['race'],model=model,market=market,
                    forecast_cumulative=data['cumulative'],**settle(data['tickets'],actual['payouts'][market],actual['nonstarters'])))
        summaries[model]=aggregate(group)
    old=[]
    for r in fallback:
        name=f"{r['track']}{r['race']}R"
        weights={h['number']:h['relative_weight_pct'] for h in r['horses']}
        row=dict(date='20261024',race=name,model='POSTRACE_FALLBACK',**evaluate(weights,results['20261024',name]))
        old.append(row);rows.append(row)
    summaries['POSTRACE_FALLBACK']=aggregate(old)
    totals=[]
    for model,market in itertools.product('ABCD',('single','quinella','trio')):
        group=[r for r in settlements if r['model']==model and r['market']==market]
        total={'model':model,'market':market,'races':len(group)}
        for key in ('points','hypothetical_stake_yen','hypothetical_payout_yen','hypothetical_refund_yen','hit_tickets','hit_race'):
            total[key]=sum(r[key] for r in group)
        total['hypothetical_gross_return_pct']=100*(total['hypothetical_payout_yen']+total['hypothetical_refund_yen'])/total['hypothetical_stake_yen']
        totals.append(total)
    kikka=[]
    actual=results['20261025','京都11R']
    for version,models in [('morning_and_1515',next(r for r in forecasts if r['race']=='京都11R')['models']),
                           ('1342_market20',markdown_variant(ROOT/'reports/20261025_kikukasho_1342_market_sensitivity_full_tickets.md'))]:
        for model,m in models.items():
            weights={h['no']:h['p1'] for h in m['horses']}
            marginal,triples=rank_distribution(weights)
            wide={pair:wide_union(triples,[pair]) for pair in itertools.combinations(sorted(weights),2)}
            best=sorted(wide,key=lambda pair:(-wide[pair],pair))[:3]
            kikka.append(dict(version=version,model=model,**evaluate(weights,actual),
                tickets={market:settle(data['tickets'] if isinstance(data,dict) else data,actual['payouts'][market]) for market,data in m['priority'].items()},
                wide_top3_diagnostic=[{'numbers':list(pair),'p':wide[pair],'hit':'-'.join(map(str,pair)) in actual['payouts']['wide']} for pair in best],
                wide_top3_union=wide_union(triples,best),
                wide_winning_pairs=[{'numbers':key,'p':wide[tuple(map(int,key.split('-')))],'payout_yen':value} for key,value in actual['payouts']['wide'].items()]))
    diagnostics=calibrate_diagnostic(forecasts,results)
    updates=[]
    for r in six_race_variants(ROOT/'reports/20261025_new_standard_six_races_day_of_update_1000.md'):
        actual=results['20261025',r['race']]
        updates.append(dict(race=r['race'],model=r['model'],
            saved_preoff_proven=r['race']!='京都1R',
            **evaluate({h['no']:h['p1'] for h in r['horses']},actual),
            tickets={k:settle(v,actual['payouts'][k],actual['nonstarters']) for k,v in r['priority'].items()}))
    payload=dict(status='RESEARCH_RECONCILIATION_OFFICIAL_PENDING',actual_purchase_evidence=False,actual_roi=None,
        official_forward_count_added=0,results_races=72,frozen_research_races=35,retrospective_races=36,
        excluded=[{'date':'20261025','race':'東京4R','reason':'No prediction: obstacle outside model domain'}],
        top3_definition='Frozen p1 descending, ties by horse number; accepted payout sets/orders handle third-place ties.',
        brier_definition='Per-race sum over all frozen runners, then race mean; p1 only.',
        hypothetical_returns='100 yen per stored selected ticket, includes refunds; not actual bets or budget-5000 portfolios.',
        summaries=summaries,ticket_totals=totals,kikka=kikka,day_of_six_race_update=updates,
        calibration_diagnostic=diagnostics)
    for name,data in [('review.json',payload),('race_scores.json',rows),('ticket_settlement.json',settlements)]:
        (OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    fields=['date','race','actual_top3','status','A_top3','A_hit','B_top3','B_hit','C_top3','C_hit','D_top3','D_hit','fallback_top3','fallback_hit']
    bykey={(r['date'],r['race'],r['model']):r for r in rows}
    with (OUT/'all_72_races.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for actual in observations['races']:
            item=dict(date=actual['date'],race=actual['race'],actual_top3=';'.join(f'{rank}:{no}' for rank,no in actual['top3']),status=actual['status'])
            for model,label in [('A','A'),('B','B'),('C','C'),('D','D'),('POSTRACE_FALLBACK','fallback')]:
                row=bykey.get((actual['date'],actual['race'],model))
                if row:item[label+'_top3']='-'.join(map(str,row['top3']));item[label+'_hit']=row['top1_hit']
            w.writerow(item)
    print(json.dumps({'summaries':summaries,'ticket_totals':totals,'calibration':diagnostics},ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
