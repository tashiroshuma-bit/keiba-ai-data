"""Scenario distributions, timestamped exact-combination EV, capped virtual sizing."""
import datetime as dt
import math
from backtest_engine import podium
from features import number, timestamp
from fitted_model import softmax


def scenario_distribution(model, features, weights=None, pace_strength=.15):
    # Hypotheses, not fitted pace probabilities. Freeze weights before observing results.
    model.predict(features)  # enforce model's temporal boundary
    weights = weights or {'slow': 1/3, 'average': 1/3, 'high': 1/3}
    if set(weights) != {'slow', 'average', 'high'} or any(not math.isfinite(v) or v < 0 for v in weights.values()) or abs(sum(weights.values()) - 1) > 1e-9:
        raise ValueError('scenario weights must be a probability simplex')
    if not math.isfinite(pace_strength) or not 0 <= pace_strength <= 1:
        raise ValueError('invalid pace strength')
    base = model.scores(features)
    rank = [[0., 0., 0.] for _ in features]
    pairs, triples, scenarios = {}, {}, {}
    adjustment = [(f['front_rate'] - .5) if f['style_observed'] else 0 for f in features]
    for name, direction in [('slow', 1), ('average', 0), ('high', -1)]:
        p = softmax([s + direction * pace_strength * a for s, a in zip(base, adjustment)], model.temperature)
        r, pair, triple = podium(p.tolist())
        scenarios[name] = p.tolist()
        w = weights[name]
        for i in range(len(features)):
            for k in range(3):
                rank[i][k] += w * r[i][k]
        for target, source in ((pairs, pair), (triples, triple)):
            for key, value in source.items():
                target[key] = target.get(key, 0) + w * value
    return rank, pairs, triples, scenarios


def validate_field(rows, cutoff_minutes=5, max_odds_age_minutes=60, require_odds=True):
    if len(rows) < 3:
        raise ValueError('at least three active runners required')
    for field in ('race_id', 'off_timestamp', 'track', 'surface', 'distance_m'):
        if any(not r.get(field) for r in rows) or len({r[field] for r in rows}) != 1:
            raise ValueError(f'missing/inconsistent {field}')
    for field in ('horse_id', 'horse_number'):
        if len({r.get(field) for r in rows}) != len(rows) or any(not r.get(field) for r in rows):
            raise ValueError('duplicate/missing ' + field)
    if any(not str(r['horse_number']).isdigit() or int(r['horse_number']) < 1 or str(int(r['horse_number'])) != str(r['horse_number']) for r in rows):
        raise ValueError('horse numbers must be canonical positive integers')
    if any(r.get('field_complete') != 'yes' for r in rows):
        raise ValueError('complete active field must be attested')
    if any(r.get('scratched', 'no') != 'no' for r in rows):
        raise ValueError('remove scratches and re-attest complete field before prediction')
    if cutoff_minutes < 0 or max_odds_age_minutes < 0:
        raise ValueError('invalid time limits')
    cutoff = timestamp(rows[0]['off_timestamp']) - dt.timedelta(minutes=cutoff_minutes)
    if number(rows[0]['distance_m']) <= 0:
        raise ValueError('invalid distance')
    for r in rows:
        if not r.get('source_url', '').startswith('https://'):
            raise ValueError('runner provenance required')
        for field in ('features_asof', 'going_asof'):
            if r.get(field) and timestamp(r[field]) > cutoff:
                raise ValueError('future ' + field)
        if r.get('going') and not r.get('going_asof'):
            raise ValueError('current going requires observation timestamp')
        if r.get('carried_weight') and not r.get('features_asof'):
            raise ValueError('current weight requires features_asof')
        if require_odds:
            validate_quote(r, cutoff, max_odds_age_minutes, 'pre_off_odds')
    return cutoff


def validate_quote(quote, cutoff, max_age=60, odds_field='decimal_odds'):
    odds = number(quote.get(odds_field))
    if odds is None or odds <= 1:
        raise ValueError('missing/invalid pre-off odds')
    at = timestamp(quote['odds_timestamp'])
    if at > cutoff or (cutoff - at).total_seconds() > max_age * 60:
        raise ValueError('late or stale odds')
    if not quote.get('source_url', '').startswith('https://'):
        raise ValueError('odds provenance required')
    return odds


def opportunities(rows, features, rank, pairs, triples, scenarios, cutoff, quotes=()):
    numbers = {str(r['horse_number']): i for i, r in enumerate(rows)}
    candidates = []
    def add(kind, indexes, quote, field='decimal_odds'):
        odds = validate_quote(quote, cutoff, odds_field=field)
        if kind == 'win':
            p = rank[indexes[0]][0]
        elif kind == 'wide':
            p = pairs[tuple(sorted(indexes))]
        else:
            p = triples[tuple(sorted(indexes))]
        # Conservative heuristic haircut, not a statistical confidence interval.
        missing = sum(features[i]['history_starts'] < 3 for i in indexes) / len(indexes)
        scenario_spread = max(max(s[i] for s in scenarios.values()) - min(s[i] for s in scenarios.values()) for i in indexes)
        haircut = min(.8, .1 + .35 * missing + scenario_spread)
        lower = p * (1 - haircut)
        candidates.append({'kind': kind, 'horse_numbers': [str(rows[i]['horse_number']) for i in indexes],
                           'probability': p, 'decimal_odds': odds, 'expected_return': p * odds,
                           'conservative_probability': lower, 'conservative_return': lower * odds,
                           'uncertainty_haircut': haircut})
    for i, r in enumerate(rows):
        if r.get('pre_off_odds') and r.get('odds_timestamp'):
            add('win', [i], r, 'pre_off_odds')
    seen = set()
    for q in quotes:
        kind = q['kind']
        if kind not in ('wide', 'trio') or q.get('race_id') != rows[0]['race_id']:
            raise ValueError('invalid combination market')
        ns = q['horse_numbers']
        if len(ns) != (2 if kind == 'wide' else 3) or len(set(ns)) != len(ns) or any(str(n) not in numbers for n in ns):
            raise ValueError('invalid combination runners')
        ix = tuple(sorted(numbers[str(n)] for n in ns))
        if (kind, ix) in seen:
            raise ValueError('duplicate combination quote')
        seen.add((kind, ix))
        add(kind, ix, q)
    return sorted(candidates, key=lambda c: c['expected_return'], reverse=True)


def allocate(candidates, bankroll, race_budget=5000, open_exposure=0, unit=100,
             race_fraction=.02, exposure_fraction=.1, min_return=1.05):
    for value in (bankroll, race_budget, open_exposure, race_fraction, exposure_fraction, min_return):
        if not math.isfinite(value) or value < 0:
            raise ValueError('invalid risk setting')
    if unit < 1 or not isinstance(unit, int) or race_fraction > 1 or exposure_fraction > 1 or min_return < 1:
        raise ValueError('invalid risk limits')
    cap = max(0, min(race_budget, bankroll * race_fraction, bankroll * exposure_fraction - open_exposure))
    remaining = int(cap // unit) * unit
    bets, rejected = [], []
    for c in sorted(candidates, key=lambda c: c['conservative_return'], reverse=True):
        if c['conservative_return'] < min_return:
            rejected.append({**c, 'reason': 'insufficient conservative expected return'})
            continue
        odds, p = c['decimal_odds'], c['conservative_probability']
        kelly = max(0, (p * odds - 1) / (odds - 1)) * .25
        stake = min(remaining, int(bankroll * kelly // unit) * unit)
        if stake < unit:
            rejected.append({**c, 'reason': 'risk cap or stake below unit'})
            continue
        bets.append({**c, 'stake_yen': stake, 'mode': 'virtual'})
        remaining -= stake
    return {'bets': bets, 'rejected': rejected, 'stake_yen': sum(b['stake_yen'] for b in bets),
            'cap_yen': int(cap // unit) * unit, 'decision': 'bet' if bets else 'skip'}
