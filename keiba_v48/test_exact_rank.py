import copy
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from exact_rank_model import ExactRankTree,exact_set,matrix
from exact_rank_research import choose,exact_record
from ranking_model import augment,joint_distribution
from test_ranking import race
from rank_forecast import forecast
from completion_validation import sha


class ExactRankTests(unittest.TestCase):
    def test_exact_set_can_differ_from_marginal_top_three(self):
        q=np.zeros((5,5,5));q[0,1,2]=.4;q[0,3,4]=.3;q[1,3,4]=.3
        marginal=q.sum(axis=(1,2))+q.sum(axis=(0,2))+q.sum(axis=(0,1))
        old=set(sorted(range(5),key=lambda i:(-marginal[i],i))[:3])
        selected,mass=exact_set(q,['1','2','3','4','5'])
        self.assertNotEqual(old,{0,1,2})
        self.assertEqual(selected,[0,1,2]);self.assertAlmostEqual(mass,.4)

    def test_exact_set_tie_break_and_invalid_distribution(self):
        _,q=joint_distribution(np.zeros((3,4)))
        selected,mass=exact_set(q,['8','2','5','1'])
        self.assertEqual({['8','2','5','1'][i] for i in selected},{'1','2','5'})
        self.assertAlmostEqual(mass,.25)
        with self.assertRaises(ValueError):exact_set(q*2,['8','2','5','1'])

    def test_training_reload_and_no_market_features(self):
        rs=[augment(race(i)) for i in range(4)]
        for r in rs:
            for row in r['rows']:row.update(distance_m=1600,surface='turf',class_level=0)
        poisoned=copy.deepcopy(rs)
        for r in poisoned:
            for row in r['rows']:row.update(final_win_odds=9999,payouts={'x':99999},finish_position=99)
        np.testing.assert_array_equal(matrix(rs),matrix(poisoned))
        for family in ('win','shared_top3','stagewise_top3'):
            m=ExactRankTree().fit(rs,family,trees=8,minimum_leaf=2,regularization=1)
            restored=ExactRankTree.from_dict(json.loads(json.dumps(m.to_dict())))
            a=m.raw(rs,enforce_time=False);b=restored.raw(rs,enforce_time=False)
            for x,y in zip(a,b):np.testing.assert_array_equal(x,y)
            self.assertTrue(any(np.abs(x).max()>0 for x in a))
            with self.assertRaises(ValueError):m.raw(rs)
            invalid=m.to_dict();invalid['live_eligible']=True
            with self.assertRaises(ValueError):ExactRankTree.from_dict(invalid)

    def test_selection_will_not_sacrifice_one_target(self):
        metrics=dict(races=1000,winner_hit=.3,ordered_all_hit=.05,top3_all_hit=.1,joint_log_loss=2)
        grid=[dict(name='incumbent_original',metrics=metrics),
              dict(name='sacrifice_winner',metrics={**metrics,'winner_hit':.29,'ordered_all_hit':.5,'top3_all_hit':.6}),
              dict(name='improved',metrics={**metrics,'winner_hit':.31,'ordered_all_hit':.06,'top3_all_hit':.11})]
        selected,checks=choose(grid,metrics)
        self.assertEqual(selected['name'],'improved')
        self.assertFalse(next(g['eligible'] for g in checks if g['name']=='sacrifice_winner'))

    def test_tree_shadow_supports_exact_set_policy(self):
        rs=[augment(race(i)) for i in range(4)]
        for r in rs:
            for row in r['rows']:row.update(distance_m=1600,surface='turf')
        model=ExactRankTree().fit(rs,'stagewise_top3',trees=3,minimum_leaf=2)
        now=dt.datetime.now(dt.timezone.utc)
        rows=[dict(race_id='future',horse_number=str(i+1),horse_id=f'jra:{i+1}',jockey_id='jra:1',
                   track='東京',surface='turf',distance_m=1600,sex_age='牡3',field_complete='yes',expected_runners=4,
                   off_timestamp=(now+dt.timedelta(days=2)).isoformat(),features_asof=now.isoformat(),
                   source_url='https://example.test/card') for i in range(4)]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);m=root/'m.json';s=root/'s.json';db=root/'db'
            m.write_text(json.dumps(model.to_dict()));db.write_bytes(b'fixture')
            s.write_text(json.dumps(dict(model_sha256=sha(m),selection_end='2024-12-31T12:00:00+09:00',prediction_set_policy='exact_set')))
            with patch('rank_forecast.load_observed_enriched',return_value=[]):
                value=forecast(db,rows,m,s)
                self.assertEqual(value['unordered_decision_policy'],'exact_set')
                self.assertEqual(len(set(value['top3_pick'])),3)
                self.assertAlmostEqual(sum(x['p_first'] for x in value['runners']),1)


if __name__=='__main__':unittest.main()
