import copy
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from features import ENRICHED_FEATURE_NAMES
from ranking_model import RankModel, augment, joint_distribution, picks, top3_labels
from ranking_research import record, aggregate, conditional_loss
from rank_forecast import forecast
from completion_validation import sha


def race(index=0, year=2023):
    off = f'{year}-01-{index+1:02d}T12:00:00+09:00'
    fs = [dict(horse_id=f'jra:{i+1}', group='東京/turf', groups=['東京/turf', 'class:nongraded'],
               cutoff_timestamp=f'{year}-01-{index+1:02d}T11:55:00+09:00',
               values=[float(4-i)] + [0.]*(len(ENRICHED_FEATURE_NAMES)-1)) for i in range(4)]
    rows = [dict(horse_number=str(i+1), sex_age='牡3', jockey_id='jra:1',
                 finish_position=i+1, horse_identity_missing=False) for i in range(4)]
    return dict(race_id=f'{year}-{index}', off_timestamp=off, result_available_at=f'{year}-01-{index+1:02d}T13:00:00+09:00',
                features=fs, rows=rows, winner_index=0)


class RankTests(unittest.TestCase):
    def test_joint_normalization_and_no_duplicate_occupants(self):
        p, q = joint_distribution(np.zeros((3, 4)))
        np.testing.assert_allclose(p, np.ones((4, 3))/4)
        self.assertAlmostEqual(q.sum(), 1)
        self.assertTrue(np.all(p.sum(axis=1) <= 1 + 1e-12))
        for i in range(4):
            self.assertEqual(q[i, i].sum() + q[i, :, i].sum() + q[:, i, i].sum(), 0)
        p, q = joint_distribution(np.array([[1000, -1000, 0]]*3))
        self.assertTrue(np.isfinite(q).all())
        self.assertAlmostEqual(q.sum(), 1)

    def test_known_three_runner_distribution_and_tie_break(self):
        p, q = joint_distribution(np.zeros((3, 3)))
        np.testing.assert_allclose(p, np.ones((3, 3))/3)
        winner, trio, ordered = picks(p, q, ['8', '2', '5'])
        self.assertEqual(winner, 1)
        self.assertEqual(ordered, [1, 2, 0])
        self.assertEqual(set(trio), {0, 1, 2})

    def test_outcome_and_odds_do_not_enter_features(self):
        a = race(); b = copy.deepcopy(a)
        for row in b['rows']:
            row.update(final_win_odds=9999, win_payout_100=999999, finish_position=99, payouts={'win:1':9999})
        self.assertEqual([f['values'] for f in augment(a)['features']], [f['values'] for f in augment(b)['features']])
        self.assertEqual(len(a['features'][0]['values']), len(ENRICHED_FEATURE_NAMES))

    def test_rank_learning_reload_and_time_guard(self):
        rs = [augment(race(i)) for i in range(4)]
        for family in ('win', 'shared_top3', 'stagewise_top3'):
            m = RankModel().fit(rs, family=family, iterations=80)
            self.assertLess(conditional_loss(m, rs, 1), (np.log(4)+np.log(3)+np.log(2))/3)
            restored = RankModel.from_dict(json.loads(json.dumps(m.to_dict())))
            p, q = m.predict(rs[0]['features'], enforce_time=False)
            np.testing.assert_array_equal(p, restored.predict(rs[0]['features'], enforce_time=False)[0])
            with self.assertRaises(ValueError):
                restored.predict(rs[0]['features'])
            bad = m.to_dict(); bad['live_eligible'] = True
            with self.assertRaises(ValueError):
                RankModel.from_dict(bad)
        with self.assertRaises(ValueError):
            RankModel().fit([augment(race(year=2025))])

    def test_ties_are_not_given_artificial_order(self):
        r = race(); r['rows'][2]['finish_position'] = 2
        with self.assertRaises(ValueError):
            top3_labels(r)

    def test_metrics_distinguish_membership_from_order(self):
        r = race(); q = np.zeros((4,4,4)); q[2,1,0] = 1
        p = np.column_stack((q.sum(axis=(1,2)), q.sum(axis=(0,2)), q.sum(axis=(0,1))))
        result = record(r, p, q)
        self.assertEqual(result['top3_recall'], 1)
        self.assertEqual(result['top3_all_hit'], 1)
        self.assertEqual(result['ordered_all_hit'], 0)
        self.assertEqual(result['winner_hit'], 0)
        self.assertEqual(aggregate([result])['races'], 1)

    def test_shadow_forecast_uses_observed_history_and_no_bets(self):
        model = RankModel().fit([augment(race(i)) for i in range(4)], iterations=10)
        now = dt.datetime.now(dt.timezone.utc)
        rows = [dict(race_id='future', off_timestamp=(now+dt.timedelta(days=2)).isoformat(),
                     horse_id=f'jra:{i+1}', horse_number=str(i+1), jockey_id='jra:1',
                     track='東京', surface='turf', distance_m=1600, features_asof=now.isoformat(),
                     sex_age='牡3', field_complete='yes', expected_runners=4, source_url='https://example.test/card') for i in range(4)]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); m = root/'model.json'; selection = root/'selection.json'; db = root/'db'
            m.write_text(json.dumps(model.to_dict())); db.write_bytes(b'fixture')
            selection.write_text(json.dumps(dict(model_sha256=sha(m), selection_end='2024-12-31T12:00:00+09:00')))
            with patch('rank_forecast.load_observed_enriched', return_value=[]) as observed:
                result = forecast(db, rows, m, selection)
                self.assertEqual(observed.call_count, 1)
                self.assertLessEqual(observed.call_args.args[1], dt.datetime.now(dt.timezone.utc))
                self.assertEqual(result['allocation'], dict(bets=[], stake_yen=0))
                self.assertEqual(result['deployment_status'], 'experimental_rank_shadow')
                self.assertAlmostEqual(sum(r['p_first'] for r in result['runners']), 1)
                self.assertEqual(len(set(result['ordered_pick'])), 3)
                calibration=root/'calibration.json'
                calibration.write_text(json.dumps(dict(schema='keiba-rank-uniform-joint-calibration-v1',
                    alpha=.1,model_sha256=sha(m),base_selection_sha256=sha(selection),
                    selection_year=2024,research_only=True,selection_end='2024-12-31T12:00:00+09:00')))
                corrected=forecast(db,rows,m,selection,calibration)
                for key in ('winner_pick','ordered_pick','top3_pick'):
                    self.assertEqual(corrected[key],result[key])
                np.testing.assert_allclose([r['p_first'] for r in corrected['runners']],
                    [.9*r['p_first']+.1/4 for r in result['runners']])
                self.assertEqual(corrected['probability_calibration']['alpha'],.1)
                for bad in ({'finish_position':1}, {'final_win_odds':10}, {'pre_off_odds':10},
                            {'features_asof':(now+dt.timedelta(hours=1)).isoformat()},
                            {'off_timestamp':(now-dt.timedelta(hours=1)).isoformat()}):
                    invalid = [{**row, **bad} for row in rows]
                    with self.assertRaises(ValueError):
                        forecast(db, invalid, m, selection)
            selection.write_text(json.dumps(dict(model_sha256='0'*64, selection_end='2024-12-31T12:00:00+09:00')))
            with self.assertRaises(ValueError):
                forecast(db, rows, m, selection)


if __name__ == '__main__':
    unittest.main()
