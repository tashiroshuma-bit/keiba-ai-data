"""Synthetic regression tests; no claim of historical predictive performance."""
import csv
import datetime as dt
import itertools
import json
import math
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

import numpy as np
from features import IdentityMap, integrate_histories, build_features, FEATURE_NAMES
from fitted_model import HierarchicalModel, softmax
from improvements import predict, training_races
from model import market_probs, podium_probabilities
from strategy import validate_field, scenario_distribution, opportunities, allocate
from validation import Ledger, paired_report, equity_report


def field(year=2025, month=6, day=1, name=None):
    race = name or f'{year}-{month}-{day}'
    off = f'{year}-{month:02}-{day:02}T15:40:00+09:00'
    return [dict(race_id=race, horse_id=f'jra:H{i}', jockey_id=f'jra:J{i}',
                 horse_number=str(i), horse_name=f'SYNTHETIC{i}', off_timestamp=off,
                 result_available_at=f'{year}-{month:02}-{day:02}T16:00:00+09:00',
                 race_date=f'{year}-{month:02}-{day:02}', track='Tokyo', surface='turf', distance_m='2000',
                 going='good', going_asof=f'{year}-{month:02}-{day:02}T12:00:00+09:00',
                 carried_weight='56', features_asof=f'{year}-{month:02}-{day:02}T12:00:00+09:00',
                 odds_timestamp=f'{year}-{month:02}-{day:02}T15:30:00+09:00',
                 pre_off_odds=str([2.5, 4, 10][i-1]), source_url='https://example.org/synthetic',
                 finish_position=str(i), field_size='3', class_level='2',
                 corner4_position=str(i), last_3f_rank=str(i), relative_speed_z=str(2-i),
                 field_complete='yes') for i in (1, 2, 3)]


def trained():
    history = field(2022)
    train = training_races(history, field(2023))
    model = HierarchicalModel().fit(train, iterations=60)
    model.calibrate(training_races(history, field(2024)))
    return history, model


class HistoryTests(unittest.TestCase):
    def test_all_starts_graded_and_non_graded(self):
        rows = [*field(2022), *field(2023, 1), *field(2023, 2), *field(2023, 3), *field(2023, 4), *field(2023, 5)]
        f = build_features(rows, field())
        self.assertEqual(f[0]['history_starts'], 6)
        self.assertEqual(f[0]['course_samples'], 6)

    def test_dedup_and_conflict(self):
        h = field(2022)
        self.assertEqual(len(integrate_histories([h, h])), 3)
        with self.assertRaisesRegex(ValueError, 'conflicting'):
            integrate_histories([h, [{**h[0], 'finish_position': '3'}]])

    def test_late_same_race_future_excluded(self):
        h = field(2022)
        for row in h:
            row['result_available_at'] = '2025-06-01T15:36:00+09:00'
        self.assertEqual(build_features(h + field(), field())[0]['history_starts'], 0)

    def test_alias_review_and_namespace(self):
        aliases = [dict(kind='horse', alias='old:1', canonical='jra:H1', verified='yes', source_url='https://example.org/id')]
        ids = IdentityMap(aliases)
        self.assertEqual(ids.resolve('horse', 'old:1'), 'jra:H1')
        for value in ('horse name', '', '123'):
            with self.assertRaises(ValueError):
                ids.resolve('horse', value)
        with self.assertRaises(ValueError):
            IdentityMap([{**aliases[0], 'verified': 'no'}])
        with self.assertRaises(ValueError):
            IdentityMap(aliases + [{**aliases[0], 'canonical': 'jra:H2'}])

    def test_recent_class_rest_and_conditions(self):
        h = field(2022)
        f = build_features(h, field())[0]
        self.assertGreater(f['values'][1], 1)
        self.assertGreater(f['values'][2], 0)
        self.assertGreater(f['values'][3], .25)
        self.assertTrue(f['style_observed'])
        self.assertEqual(f['values'][-1], 1)

    def test_target_labels_never_features(self):
        rows = field()
        expected = build_features(field(2022), rows)
        changed = [{**r, 'finish_position': '99', 'final_win_odds': '9999', 'popularity': '1'} for r in rows]
        self.assertEqual(expected, build_features(field(2022), changed))

    def test_missing_going_not_fabricated(self):
        h, m = trained()
        rows = field()
        for r in rows:
            del r['going']; del r['going_asof']
        result = predict(m, h, rows)
        self.assertEqual(result['axes']['going'], [])
        self.assertIsNone(result['runners'][0]['going_suitability'])

    def test_nonfinite_history(self):
        h = field(2022); h[0]['relative_speed_z'] = 'nan'
        with self.assertRaises(ValueError):
            build_features(h, field())


class ModelTests(unittest.TestCase):
    def test_fit_calibrate_roundtrip(self):
        h, m = trained()
        features = build_features(h, field())
        p = m.predict(features)
        self.assertAlmostEqual(sum(p), 1)
        self.assertTrue(np.isfinite(p).all())
        self.assertGreater(p[0], p[2])
        other = HierarchicalModel.from_dict(json.loads(json.dumps(m.to_dict())))
        np.testing.assert_allclose(p, other.predict(features))

    def test_unseen_group_shrinks_to_global(self):
        h, m = trained()
        f = build_features(h, [{**r, 'track': 'Kyoto'} for r in field()])
        self.assertAlmostEqual(sum(m.predict(f)), 1)

    def test_calibration_time_and_overlap(self):
        h, m = trained()
        with self.assertRaises(ValueError):
            m.calibrate(training_races(h, field(2023)))
        with self.assertRaises(ValueError):
            m.predict(build_features(h, field(2024)))

    def test_calibration_improves_its_validation_objective(self):
        h, m = trained()
        report = m.calibrate(training_races(h, field(2024)))
        self.assertLessEqual(report['after_log_loss'], report['before_log_loss'])

    def test_extreme_probabilities_stable(self):
        p = softmax([700, 0, -700])
        ranks = podium_probabilities(p)
        self.assertTrue(np.isfinite(ranks).all())
        np.testing.assert_allclose(ranks.sum(axis=0), [1, 1, 1])
        for odds in ([2, float('nan'), 5], [2, float('inf'), 5]):
            with self.assertRaises(ValueError):
                market_probs(odds)

    def test_bad_model_rejected(self):
        _, m = trained()
        artifact = m.to_dict(); artifact['scale'][0] = 0
        with self.assertRaises(ValueError):
            HierarchicalModel.from_dict(artifact)


class StrategyTests(unittest.TestCase):
    def test_exact_full_field_combination_conservation(self):
        h, m = trained()
        fs = build_features(h, field())
        rank, pairs, triples, _ = scenario_distribution(m, fs)
        np.testing.assert_allclose(np.asarray(rank).sum(axis=0), [1, 1, 1])
        self.assertAlmostEqual(sum(pairs.values()), 3)
        self.assertAlmostEqual(sum(triples.values()), 1)
        self.assertAlmostEqual(triples[(0, 1, 2)], 1)

    def test_slow_high_style_sensitivity(self):
        h = field(2022)
        for row in h:
            row['field_size'] = '10'
            row['corner4_position'] = '1' if row['horse_number'] == '1' else '10'
        _, m = trained()
        fs = build_features(h, field())
        *_, scenarios = scenario_distribution(m, fs)
        self.assertGreater(scenarios['slow'][0], scenarios['high'][0])

    def test_scenario_simplex(self):
        h, m = trained()
        with self.assertRaises(ValueError):
            scenario_distribution(m, build_features(h, field()), {'slow': .8, 'average': .8, 'high': .8})

    def test_timestamp_quote_and_field_gates(self):
        for change in ({'pre_off_odds': 'nan'}, {'odds_timestamp': '2025-06-01T15:36:00+09:00'},
                       {'odds_timestamp': '2025-05-31T15:30:00+09:00'}, {'scratched': 'yes'},
                       {'field_complete': 'no'}, {'features_asof': '2025-06-01T15:41:00+09:00'},
                       {'off_timestamp': '2025-06-01T15:40:00'}, {'horse_id': 'jra:H2'}):
            with self.subTest(change=change):
                rows = field(); rows[0].update(change)
                with self.assertRaises((ValueError, TypeError)):
                    validate_field(rows)

    def test_missing_odds_predict_but_skip(self):
        h, m = trained(); rows = field(); rows[0]['pre_off_odds'] = ''
        result = predict(m, h, rows)
        self.assertEqual(result['allocation']['decision'], 'skip')
        self.assertEqual(result['allocation']['stake_yen'], 0)
        self.assertEqual(result['axes']['expected_value'], [])
        self.assertTrue(all(r['exclusion_reasons'] for r in result['runners']))

    def test_combination_ev_and_invalid_quote(self):
        h, m = trained(); rows = field(); fs = build_features(h, rows)
        rank, pairs, triples, scenarios = scenario_distribution(m, fs)
        cutoff = validate_field(rows)
        quote = dict(race_id=rows[0]['race_id'], kind='trio', horse_numbers=['1', '2', '3'],
                     decimal_odds=2., odds_timestamp=rows[0]['odds_timestamp'], source_url=rows[0]['source_url'])
        cs = opportunities(rows, fs, rank, pairs, triples, scenarios, cutoff, [quote])
        trio = next(c for c in cs if c['kind'] == 'trio')
        self.assertAlmostEqual(trio['expected_return'], 2.)
        self.assertLess(trio['conservative_return'], trio['expected_return'])
        with self.assertRaises(ValueError):
            opportunities(rows, fs, rank, pairs, triples, scenarios, cutoff, [quote, quote])

    def test_risk_caps_fraction_unit_and_skip(self):
        c = dict(conservative_return=1.8, conservative_probability=.6, decimal_odds=3.)
        a = allocate([c, c, c], 100000, race_budget=5000, open_exposure=9500)
        self.assertLessEqual(a['stake_yen'], 500)
        self.assertTrue(all(b['stake_yen'] % 100 == 0 for b in a['bets']))
        self.assertEqual(allocate([c], 100000, open_exposure=10000)['decision'], 'skip')
        self.assertEqual(allocate([{**c, 'conservative_return': .99}], 100000)['decision'], 'skip')
        with self.assertRaises(ValueError):
            allocate([c], float('nan'))


class ValidationTests(unittest.TestCase):
    def test_forward_rejects_backdating_replay_immutable(self):
        h, m = trained(); prediction = predict(m, h, field())
        ledger = Ledger(':memory:')
        with self.assertRaises(ValueError):
            ledger.freeze(prediction, m.to_dict())
        key = ledger.freeze(prediction, m.to_dict(), 'replay')
        with self.assertRaises(sqlite3.IntegrityError):
            ledger.freeze(prediction, m.to_dict(), 'replay')
        with self.assertRaises(sqlite3.IntegrityError):
            ledger.db.execute('UPDATE predictions SET mode="forward" WHERE id=?', (key,))

    def test_settlement_requires_official_payout_no_odds_substitution(self):
        h, m = trained(); prediction = predict(m, h, field())
        prediction['allocation'] = {'bets': [dict(kind='win', horse_numbers=['1'], stake_yen=100)], 'stake_yen': 100}
        ledger = Ledger(':memory:'); key = ledger.freeze(prediction, m.to_dict(), 'replay')
        result = dict(race_id=prediction['race_id'], finishes={'1': 1, '2': 2, '3': 3},
                      source_url='https://example.org/result', result_available_at='2025-06-01T16:00:00+09:00')
        s = ledger.settle(key, result)
        self.assertFalse(s['fully_settled']); self.assertIsNone(s['payout_yen'])
        other = Ledger(':memory:'); key2 = other.freeze(prediction, m.to_dict(), 'replay')
        result['payouts_per_100'] = {'win:1': 250}
        self.assertEqual(other.settle(key2, result)['payout_yen'], 250)

    def test_paired_metrics_and_bootstrap(self):
        records = [dict(race_id='R', baseline=[.3, .3, .4], candidate=[.6, .2, .2], winner_index=0)]
        report = paired_report(records)
        self.assertLess(report['log_loss_delta'], 0)
        self.assertTrue(report['win_calibration'])
        with self.assertRaises(ValueError):
            paired_report(records + records)

    def test_maximum_drawdown_and_pending(self):
        report = equity_report([dict(fully_settled=True, stake_yen=100, payout_yen=0),
                                dict(fully_settled=False, stake_yen=100, payout_yen=None),
                                dict(fully_settled=True, stake_yen=100, payout_yen=300)], 1000)
        self.assertEqual(report['return_pct'], 150)
        self.assertAlmostEqual(report['maximum_drawdown'], .1)
        self.assertEqual(report['pending_races'], 1)

    def test_cli_train_predict_evaluate_end_to_end(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            def write(name, rows):
                path = root / name
                with path.open('w', newline='') as stream:
                    w = csv.DictWriter(stream, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
                return str(path)
            history = write('history.csv', field(2022))
            training = write('training.csv', field(2023) + field(2024))
            runners = write('runners.csv', field())
            model = str(root / 'model.json')
            entry = str(Path(__file__).with_name('improvements.py'))
            commands = [
                ['train', '--history', history, '--runners', training, '--model', model],
                ['predict', '--history', history, '--runners', runners, '--model', model,
                 '--ledger', str(root / 'ledger.sqlite'), '--mode', 'replay', '--output', str(root / 'prediction.json')],
                ['evaluate', '--history', history, '--runners', runners, '--model', model, '--output', str(root / 'report.json')]]
            for args in commands:
                result = subprocess.run([sys.executable, entry, *args], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads((root / 'report.json').read_text())['races'], 1)
            self.assertEqual(len(json.loads((root / 'prediction.json').read_text())['runners']), 3)



class AdditionalRegressionTests(unittest.TestCase):
    def test_combinations_match_independent_permutation_enumeration(self):
        from backtest_engine import podium
        p = [.4, .3, .2, .1]
        rank, pairs, triples = podium(p)
        expected_rank = np.zeros((4, 3)); expected_pairs = {}; expected_triples = {}
        for order in itertools.permutations(range(4)):
            mass = 1.
            remaining = list(range(4))
            for i in order:
                mass *= p[i] / sum(p[j] for j in remaining)
                remaining.remove(i)
            for k, i in enumerate(order[:3]):
                expected_rank[i, k] += mass
            for pair in itertools.combinations(sorted(order[:3]), 2):
                expected_pairs[pair] = expected_pairs.get(pair, 0) + mass
            triple = tuple(sorted(order[:3]))
            expected_triples[triple] = expected_triples.get(triple, 0) + mass
        np.testing.assert_allclose(rank, expected_rank)
        for k in pairs:
            self.assertAlmostEqual(pairs[k], expected_pairs[k])
        for k in triples:
            self.assertAlmostEqual(triples[k], expected_triples[k])

    def test_canonical_alias_collision_blocks_prediction(self):
        h, m = trained(); rows = field(); rows[1]['horse_id'] = 'old:alias'
        ids = IdentityMap([dict(kind='horse', alias='old:alias', canonical='jra:H1',
                                verified='yes', source_url='https://example.org/id')])
        with self.assertRaisesRegex(ValueError, 'canonical'):
            predict(m, h, rows, ids)

    def test_top3_calibration_is_independent_of_win(self):
        r = dict(race_id='R', baseline=[.25]*4, candidate=[.4, .3, .2, .1], winner_index=0,
                 candidate_top3=[.9, .8, .7, .6], observed_top3=[0, 1, 2])
        report = paired_report([r], bootstrap_samples=20)
        self.assertAlmostEqual(report['candidate_top3_brier'], (.01 + .04 + .09 + .36) / 4)
        self.assertTrue(report['top3_calibration'])

    def test_offline_index_never_attempts_network(self):
        from unittest.mock import patch
        from bulk_ingest import run
        with tempfile.TemporaryDirectory() as d:
            with patch('bulk_ingest.fetch', side_effect=AssertionError('unexpected network')) as fetch:
                report = run(str(Path(d) / 'db.sqlite'), str(Path(d) / 'pdfs'), index_dir=d)
                fetch.assert_not_called()
                self.assertEqual(len(report['index_errors']), 3)

    def test_calibration_cutoff_not_just_off_must_follow_training_labels(self):
        h, m = trained()
        valid = training_races(h, field(2024))
        m.train_end = '2024-06-01T15:38:00+09:00'
        with self.assertRaisesRegex(ValueError, 'calibration'):
            m.calibrate(valid)

    def test_indexed_features_equal_raw_features(self):
        from features import HistoryIndex
        h = field(2022) + field(2023)
        self.assertEqual(build_features(h, field()), build_features(HistoryIndex(h), field()))


if __name__ == '__main__':
    unittest.main()
