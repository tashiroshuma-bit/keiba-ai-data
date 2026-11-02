"""Research-only paired 6,036-race overlay stress test; NOT an A/v49-v50 replay.

Uses an archived historical *rank candidate* as the input distribution, not the
v50 standard runner's required contemporaneous internal-A probabilities.
Historical availability is assumed by a 2-day date lag, not proved by capture
metadata. Does not write to the canonical SQLite or change production policy.
"""
import argparse
import datetime as dt
import gzip
import hashlib
import json
import math
import random
import sqlite3
from collections import defaultdict
from pathlib import Path

EXPECTED_DB = '5a7dcd864286ccb60a43dd644a0fbe050ea25425e7e39effa7fa70fdc3128ebc'
EXPECTED_ARCHIVE = '4da90bea028ac9d8e9792a5e00b2897930a67c6b1252b86c0f38aac38ca32850'
EXPECTED_COUNTS = {'2025': 3329, '2026': 2707}


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def load_evidence(archive, database):
    if digest(database) != EXPECTED_DB:
        raise ValueError('canonical version10 DB SHA mismatch')
    if digest(archive) != EXPECTED_ARCHIVE:
        raise ValueError('historical archive SHA mismatch')
    with gzip.open(archive, 'rt', encoding='utf-8') as stream:
        races = json.load(stream)
    if not isinstance(races, list) or len(races) != sum(EXPECTED_COUNTS.values()):
        raise ValueError('historical cohort incomplete')
    counts = defaultdict(int)
    seen = set()
    for r in races:
        year = r['date'][:4]
        counts[year] += 1
        if r['race_id'] in seen:
            raise ValueError('duplicate historical race')
        seen.add(r['race_id'])
    if dict(counts) != EXPECTED_COUNTS:
        raise ValueError('2025/2026 cohort differs')
    con = sqlite3.connect('file:' + str(Path(database).resolve()) + '?mode=ro', uri=True)
    try:
        if con.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise ValueError('canonical database quick_check failed')
        race_rows = con.execute('''SELECT race_id,race_date,surface,status FROM annual_report_races''').fetchall()
        runner_rows = con.execute('''SELECT r.race_id,r.race_date,r.surface,x.horse_id,x.jockey_id,
                      x.finish_order,r.expected_runners,x.horse_number
                      FROM annual_report_races r JOIN annual_report_runners x ON r.race_id=x.race_id
                      WHERE r.status='validated_result' AND r.surface IN ('turf','dirt')
                        AND x.finish_order > 0
                      ORDER BY r.race_date,r.race_id,x.horse_number''').fetchall()
    finally:
        con.close()
    roster = {rid:(date,surface,status) for rid,date,surface,status in race_rows}
    per_race = defaultdict(dict)
    history = defaultdict(lambda:defaultdict(list))
    for rid,date,surface,horse,jockey,finish,n,number in runner_rows:
        per_race[rid][str(number)] = (jockey,finish)
        history[date][rid].append((surface,horse,jockey,finish,n))
    return races,roster,per_race,history


def add_history_day(day, horse_hist, rider_hist):
    """Match build_v50_rider_residuals.build's entire-day delayed update."""
    pending = []
    for field in day.values():
        valid = [(surface,h,j,finish,n) for surface,h,j,finish,n in field
                 if h and j and n and n >= 3 and finish <= n]
        if len(valid) < 3:
            continue
        abilities = [(horse_hist[h][1] + 1.2)/(horse_hist[h][0] + 8)
                     for _,h,_,_,_ in valid]
        mean = sum(abilities)/len(abilities)
        for (surface,horse,jockey,finish,n),ability in zip(valid,abilities):
            expected = .5 + .5 * math.tanh(2 * (ability - mean))
            observed = (n - finish)/(n - 1)
            pending.append((surface,horse,jockey,finish,observed-expected))
    for surface,horse,jockey,finish,residual in pending:
        rider_hist[(surface,jockey)][0] += 1
        rider_hist[(surface,jockey)][1] += residual
        horse_hist[horse][0] += 1
        horse_hist[horse][1] += {1:1.0,2:.5,3:.25}.get(finish,0)


def overlay(probabilities, adjustments, temperature):
    if not math.isfinite(temperature) or temperature <= 0:
        raise ValueError('invalid temperature')
    if any(not math.isfinite(p) or p <= 0 for p in probabilities):
        raise ValueError('invalid source probability')
    if abs(sum(probabilities)-1) > 1e-5:
        raise ValueError('source probabilities do not sum to one')
    if any(not math.isfinite(a) for a in adjustments):
        raise ValueError('nonfinite rider residual')
    logits = [(math.log(p)+a)/temperature for p,a in zip(probabilities,adjustments)]
    peak = max(logits)
    values = [math.exp(x-peak) for x in logits]
    total = sum(values)
    return [x/total for x in values]


def race_scores(numbers, truth, original, changed):
    if len(numbers) != len(original) or len(numbers) != len(changed):
        raise ValueError('race runner length mismatch')
    if len(set(numbers)) != len(numbers) or len(numbers) < 3:
        raise ValueError('duplicate or too few horse numbers')
    if len(truth) != 3 or len(set(truth)) != 3 or any(x not in numbers for x in truth):
        raise ValueError('invalid podium label')
    winner = numbers.index(truth[0])
    result = {}
    for label,p in (('base',original),('overlay',changed)):
        order = sorted(range(len(p)),key=lambda i:(-round(p[i],12),int(numbers[i])))
        pick = [numbers[i] for i in order[:3]]
        result[label] = {
            'winner_hit': int(pick[0] == truth[0]),
            'winner_top3': int(truth[0] in pick),
            'ordered_top3': int(pick == truth),
            'unordered_top3': int(set(pick) == set(truth)),
            'logloss': -math.log(p[winner]),
            'brier': sum((v-int(i == winner))**2 for i,v in enumerate(p)),
        }
    return result


def evaluate(races,roster,per_race,history,temperature=.7,lag_days=2):
    horse_hist = defaultdict(lambda:[0,0.0])
    rider_hist = defaultdict(lambda:[0,0.0])
    dates = sorted(history)
    cursor = 0
    rows = []
    excluded = []
    for r in sorted(races,key=lambda v:(v['date'],v['race_id'])):
        rid,date = r['race_id'],r['date']
        if rid not in roster or roster[rid][0] != date:
            excluded.append({'race_id':rid,'year':date[:4],'reason':'missing_or_date_mismatch'})
            continue
        if roster[rid][2] != 'validated_result':
            excluded.append({'race_id':rid,'year':date[:4],'reason':'requires_review'})
            continue
        if roster[rid][1] not in ('turf','dirt'):
            excluded.append({'race_id':rid,'year':date[:4],'reason':'unsupported_surface'})
            continue
        cutoff = (dt.date.fromisoformat(date)-dt.timedelta(days=lag_days)).isoformat()
        while cursor < len(dates) and dates[cursor] < cutoff:
            add_history_day(history[dates[cursor]],horse_hist,rider_hist)
            cursor += 1
        surface = roster[rid][1]
        if surface not in ('turf','dirt'):
            raise ValueError('unknown surface')
        numbers = r['horse_numbers']
        source = r['candidate']['marginal_probabilities']
        original = [float(p[0]) for p in source]
        actual = per_race[rid]
        if set(numbers) != set(actual):
            excluded.append({'race_id':rid,'year':date[:4],'reason':'runner_set_mismatch'})
            continue
        truth = [str(x) for x in r['candidate']['target']]
        db_truth = [str(number) for number in sorted((int(k) for k,v in actual.items() if v[1] in (1,2,3)),
                                                    key=lambda k:actual[str(k)][1])]
        if db_truth != truth:
            excluded.append({'race_id':rid,'year':date[:4],'reason':'podium_mismatch'})
            continue
        residual = []
        covered = 0
        for number in numbers:
            jockey = actual[number][0]
            if jockey and (surface,jockey) in rider_hist:
                n,total = rider_hist[(surface,jockey)]
                residual.append(total/(n+30))
                covered += 1
            else:
                residual.append(0.0)
        changed = overlay(original,residual,temperature)
        score = race_scores(numbers,truth,original,changed)
        rows.append({'race_id':rid,'date':date,'year':date[:4],
                     'runners':len(numbers),'jockey_residual_covered':covered,
                     'base':score['base'],'overlay':score['overlay']})
    return rows,excluded


def aggregate(rows):
    if not rows:
        raise ValueError('empty evaluation')
    metrics = ('winner_hit','winner_top3','ordered_top3','unordered_top3','logloss','brier')
    out = {'races':len(rows),'runners':sum(r['runners'] for r in rows),
           'jockey_residual_covered':sum(r['jockey_residual_covered'] for r in rows)}
    for model in ('base','overlay'):
        out[model] = {k:sum(r[model][k] for r in rows)/len(rows) for k in metrics}
    out['overlay_minus_base'] = {k:out['overlay'][k]-out['base'][k] for k in metrics}
    return out


def date_bootstrap(rows,draws=2000,seed=20261102):
    """Paired cluster bootstrap by race date, with race-weighted means."""
    groups = defaultdict(list)
    for row in rows:
        groups[row['date']].append(row)
    keys = sorted(groups)
    rng = random.Random(seed)
    metrics = ('winner_hit','winner_top3','ordered_top3','unordered_top3','logloss','brier')
    group_sum = {d: {k:sum(r['overlay'][k]-r['base'][k] for r in groups[d]) for k in metrics}
                 for d in keys}
    sampled = {k:[] for k in metrics}
    for _ in range(draws):
        chosen = [keys[rng.randrange(len(keys))] for _ in keys]
        count = sum(len(groups[d]) for d in chosen)
        for k in metrics:
            sampled[k].append(sum(group_sum[d][k] for d in chosen)/count)
    return {k:[sorted(v)[int(.025*draws)],sorted(v)[min(draws-1,int(.975*draws))]]
            for k,v in sampled.items()}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--archive',required=True)
    p.add_argument('--database',required=True)
    p.add_argument('--output',required=True)
    p.add_argument('--temperature',type=float,default=.7)
    args = p.parse_args()
    path = Path(args.output)
    if path.exists():
        raise FileExistsError('audit output cannot be overwritten')
    races,roster,per_race,history = load_evidence(args.archive,args.database)
    rows,excluded = evaluate(races,roster,per_race,history,args.temperature)
    by_year = {y:[r for r in rows if r['year']==y] for y in EXPECTED_COUNTS}
    excluded_by_year = {y:[r for r in excluded if r['year']==y] for y in EXPECTED_COUNTS}
    if any(len(by_year[y])+len(excluded_by_year[y]) != EXPECTED_COUNTS[y] for y in EXPECTED_COUNTS):
        raise ValueError('cohort accounting incomplete')
    exclusions = {y:dict(__import__('collections').Counter(r['reason'] for r in excluded_by_year[y]))
                  for y in EXPECTED_COUNTS}
    result = {
        'schema':'v50-research-historical-overlay-audit-v1',
        'status':'RESEARCH_ONLY_NOT_STANDARD_V50_OR_V49_DIRECT_REPLAY',
        'source':'historical_history_blend_candidate_not_internal_A',
        'base_artifact_sha256':EXPECTED_ARCHIVE,'canonical_db_sha256':EXPECTED_DB,
        'history_lag_days':2,'temperature':args.temperature,
        'temporal_limit':'2-day calendar lag assumption; original publication timestamps not verified',
        'calibration_limit':'T=0.70 chosen on 2026-10-31; 2025/2026 are already inspected retrospective cohorts',
        'source_cohort_races':EXPECTED_COUNTS,
        'eligible_paired_races':{y:len(by_year[y]) for y in EXPECTED_COUNTS},
        'excluded_by_year_reason':exclusions,
        'excluded_sample':excluded[:15],
        'results':{y:{**aggregate(v),'paired_date_bootstrap_95pct_delta':date_bootstrap(v)}
                   for y,v in by_year.items()},
        'all':{**aggregate(rows),'paired_date_bootstrap_95pct_delta':date_bootstrap(rows)},
        'production_changed':False,'live_bet_generation':False,
    }
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2)
        stream.write('\n')
    print(json.dumps({y:result['results'][y] for y in EXPECTED_COUNTS},ensure_ascii=False))


if __name__ == '__main__':
    main()
