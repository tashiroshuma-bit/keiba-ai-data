"""Append-only prediction/settlement ledger and paired probabilistic evaluation."""
import datetime as dt
import hashlib
import json
import math
import random
import sqlite3
from features import timestamp


def canonical(data):
    return json.dumps(data, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


class Ledger:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS predictions(
          id TEXT PRIMARY KEY, race_id TEXT NOT NULL, model_hash TEXT NOT NULL,
          mode TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL,
          UNIQUE(race_id,model_hash,mode));
        CREATE TABLE IF NOT EXISTS settlements(
          prediction_id TEXT PRIMARY KEY REFERENCES predictions(id),
          recorded_at TEXT NOT NULL, payload TEXT NOT NULL);
        CREATE TRIGGER IF NOT EXISTS immutable_predictions_update BEFORE UPDATE ON predictions
          BEGIN SELECT RAISE(ABORT,'predictions are append-only'); END;
        CREATE TRIGGER IF NOT EXISTS immutable_predictions_delete BEFORE DELETE ON predictions
          BEGIN SELECT RAISE(ABORT,'predictions are append-only'); END;
        CREATE TRIGGER IF NOT EXISTS immutable_settlements_update BEFORE UPDATE ON settlements
          BEGIN SELECT RAISE(ABORT,'settlements are append-only'); END;
        CREATE TRIGGER IF NOT EXISTS immutable_settlements_delete BEFORE DELETE ON settlements
          BEGIN SELECT RAISE(ABORT,'settlements are append-only'); END;
        ''')

    def freeze(self, prediction, model, mode='forward'):
        if mode not in ('forward', 'replay'):
            raise ValueError('unknown ledger mode')
        now = dt.datetime.now(dt.timezone.utc)
        cutoff = timestamp(prediction['cutoff_timestamp'])
        if mode == 'forward' and now > cutoff:
            raise ValueError('forward prediction must be frozen before cutoff; use replay for historical research')
        raw = canonical({**prediction, 'model_artifact': model})
        fingerprint = hashlib.sha256(canonical(model).encode()).hexdigest()
        key = hashlib.sha256((mode + fingerprint + raw).encode()).hexdigest()
        with self.db:
            self.db.execute('INSERT INTO predictions VALUES(?,?,?,?,?,?)',
                            (key, prediction['race_id'], fingerprint, mode, now.isoformat(), raw))
        return key

    def settle(self, prediction_id, result):
        row = self.db.execute('SELECT payload FROM predictions WHERE id=?', (prediction_id,)).fetchone()
        if not row:
            raise ValueError('unknown prediction')
        prediction = json.loads(row[0])
        finishes = {str(k): int(v) for k, v in result['finishes'].items()}
        numbers = {r['horse_number'] for r in prediction['runners']}
        if any(float(result['finishes'][k]) != v for k, v in finishes.items()):
            raise ValueError('nonintegral finishing rank')
        if result['race_id'] != prediction['race_id'] or set(finishes) != numbers or sorted(finishes.values()) != list(range(1, len(numbers) + 1)):
            raise ValueError('incomplete result or unsupported dead heat/nonfinisher')
        at = timestamp(result['result_available_at'])
        if at < timestamp(prediction['off_timestamp']) or at > dt.datetime.now(dt.timezone.utc):
            raise ValueError('invalid result publication time')
        payouts = result.get('payouts_per_100', {})
        if not result.get('source_url', '').startswith('https://'):
            raise ValueError('official result provenance required')
        resolved, unresolved = [], []
        for bet in prediction['allocation']['bets']:
            ranks = [finishes[n] for n in bet['horse_numbers']]
            hit = (ranks[0] == 1 if bet['kind'] == 'win' else all(r <= 3 for r in ranks))
            key = bet['kind'] + ':' + ','.join(sorted(bet['horse_numbers'], key=int))
            payout = payouts.get(key) if hit else 0
            if payout is None:
                unresolved.append(key)
                continue
            if not math.isfinite(float(payout)) or float(payout) < 0:
                raise ValueError('invalid official payout')
            resolved.append({'stake_yen': bet['stake_yen'], 'payout_yen': float(payout) * bet['stake_yen'] / 100})
        saved = {'result': result, 'resolved_bets': resolved, 'unresolved_winning_payouts': unresolved,
                 'fully_settled': not unresolved, 'stake_yen': prediction['allocation']['stake_yen'],
                 'payout_yen': sum(b['payout_yen'] for b in resolved) if not unresolved else None}
        with self.db:
            self.db.execute('INSERT INTO settlements VALUES(?,?,?)',
                            (prediction_id, dt.datetime.now(dt.timezone.utc).isoformat(), canonical(saved)))
        return saved


def metrics(probabilities, winner):
    p = list(probabilities)
    if len(p) < 3 or not 0 <= winner < len(p) or any(not math.isfinite(v) or v < 0 or v > 1 for v in p) or abs(sum(p) - 1) > 1e-8:
        raise ValueError('invalid win probabilities')
    return {'log_loss': -math.log(max(p[winner], 1e-12)),
            'brier': sum((v - int(i == winner)) ** 2 for i, v in enumerate(p)) / len(p),
            'top1_hit': int(max(range(len(p)), key=p.__getitem__) == winner)}


def paired_report(records, bootstrap_samples=500, seed=48):
    """Records contain same-field frozen baseline/candidate probabilities and outcomes."""
    if not records:
        raise ValueError('no paired races')
    if len({r['race_id'] for r in records}) != len(records):
        raise ValueError('duplicate evaluation race')
    scores = [(metrics(r['baseline'], r['winner_index']), metrics(r['candidate'], r['winner_index'])) for r in records]
    result = {'races': len(records), 'brier_definition': 'mean over runners, then mean over races',
              'evaluation_role': 'exploratory; 2025 is not an unseen holdout',
              'forward_target_races': 100}
    for j, name in enumerate(('baseline', 'candidate')):
        result[name] = {k: sum(s[j][k] for s in scores) / len(scores) for k in scores[0][j]}
    rng = random.Random(seed)
    differences = [b['log_loss'] - a['log_loss'] for a, b in scores]
    draws = sorted(sum(rng.choice(differences) for _ in scores) / len(scores) for _ in range(bootstrap_samples))
    result['log_loss_delta'] = sum(differences) / len(scores)
    result['race_bootstrap_95pct_delta'] = [draws[int(.025 * len(draws))], draws[min(len(draws)-1, int(.975 * len(draws)))]] if draws else None
    bins = []
    for low in range(10):
        values = [(p, int(i == r['winner_index'])) for r in records for i, p in enumerate(r['candidate']) if low / 10 <= p < (low + 1) / 10 or (low == 9 and p == 1)]
        if values:
            bins.append({'lower': low / 10, 'runners': len(values), 'predicted': sum(p for p, _ in values) / len(values), 'observed': sum(y for _, y in values) / len(values)})
    result['win_calibration'] = bins
    if all('candidate_top3' in r and 'observed_top3' in r for r in records):
        top3 = []
        errors = []
        for r in records:
            ps, actual = r['candidate_top3'], set(r['observed_top3'])
            if len(ps) != len(r['candidate']) or len(actual) != 3 or any(i < 0 or i >= len(ps) for i in actual):
                raise ValueError('invalid top3 observations')
            if any(not math.isfinite(v) or not 0 <= v <= 1 + 1e-9 for v in ps) or abs(sum(ps) - 3) > 1e-8:
                raise ValueError('invalid top3 probabilities')
            errors.append(sum((v - int(i in actual)) ** 2 for i, v in enumerate(ps)) / len(ps))
            top3.extend((v, int(i in actual)) for i, v in enumerate(ps))
        result['candidate_top3_brier'] = sum(errors) / len(errors)
        result['top3_calibration'] = []
        for low in range(10):
            values = [(v, y) for v, y in top3 if low / 10 <= v < (low + 1) / 10 or (low == 9 and v >= 1)]
            if values:
                result['top3_calibration'].append({'lower': low / 10, 'runners': len(values),
                    'predicted': sum(v for v, _ in values) / len(values),
                    'observed': sum(y for _, y in values) / len(values)})
    return result


def equity_report(settlements, initial_bankroll):
    if not math.isfinite(initial_bankroll) or initial_bankroll <= 0:
        raise ValueError('positive initial capital required')
    equity = peak = initial_bankroll
    max_dd = stakes = returns = 0.
    pending = 0
    # Caller supplies chronologically ordered race-level settlements; no partial-race ROI.
    for s in settlements:
        if not s['fully_settled']:
            pending += 1
            continue
        stakes += s['stake_yen']
        returns += s['payout_yen']
        equity += s['payout_yen'] - s['stake_yen']
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak)
    return {'initial_bankroll': initial_bankroll, 'closing_equity_settled_only': equity,
            'stake_yen': stakes, 'payout_yen': returns,
            'return_pct': 100 * returns / stakes if stakes else None,
            'maximum_drawdown': max_dd, 'pending_races': pending}
