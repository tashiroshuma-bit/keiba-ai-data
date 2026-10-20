import copy
import json
import unittest
import numpy as np
from boosted_race import BoostedRaceModel, matrix, probabilities, tree_predict
from roi95_research import decide, select_policy, interval


def race(year=2023, index=1):
    date = f'{year}-02-{index:02d}'
    rows = [dict(horse_number=str(i+1), age=3, sex='牡', distance_m=1600,
                 surface='turf', class_level=1, race_date=date,
                 final_win_odds=[2.,4.,8.][i], win_payout_100=200,
                 finish_position=i+1) for i in range(3)]
    fs = [dict(race_id=f'{year}{index}',horse_id=f'jra:h{i}',group='a/turf',
               cutoff_timestamp=date+'T09:55:00+09:00',
               values=[float(i==0)]+[0.]*22, history_starts=i,
               jockey_identity_missing=False) for i in range(3)]
    return dict(race_id=f'{year}{index}',rows=rows,features=fs,winner_index=0,
                off_timestamp=date+'T10:00:00+09:00',result_available_at=date+'T11:00:00+09:00')


class ROI95Tests(unittest.TestCase):
    def test_structural_matrix_ignores_result_and_final_odds(self):
        r=race(); a=matrix([r],'structural')[0]
        r['winner_index']=2
        for row in r['rows']:
            row.update(finish_position=3,win_payout_100=99999,final_win_odds=999.)
        np.testing.assert_array_equal(a,matrix([r],'structural')[0])

    def test_market_feature_does_not_use_result_label(self):
        r=race(); a=matrix([r],'final_market_residual')[:2]
        r['winner_index']=2
        for row in r['rows']:row.update(finish_position=3,win_payout_100=99999)
        b=matrix([r],'final_market_residual')[:2]
        for x,y in zip(a,b):np.testing.assert_array_equal(x,y)

    def test_race_probabilities_normalize_separately(self):
        p=probabilities(np.array([1000.,1001.,1002.,-100.,-101.,-102.]),[3,3])
        self.assertAlmostEqual(sum(p[:3]),1);self.assertAlmostEqual(sum(p[3:]),1)
        self.assertGreater(p[2],p[0]);self.assertGreater(p[3],p[5])
        with self.assertRaises(ValueError):probabilities(np.zeros(3),[3],0)

    def test_training_reduces_loss_and_time_guards(self):
        train=[race(index=i) for i in range(1,7)]
        m=BoostedRaceModel().fit(train,'structural',trees=20,minimum_leaf=2,leaf_regularization=1,bins=4)
        with self.assertRaisesRegex(ValueError,'follow'):m.predict(train)
        p=m.predict([race(2024)])[0]
        self.assertGreater(p[0],1/3)
        with self.assertRaisesRegex(ValueError,'2023 only'):
            BoostedRaceModel().fit([race(2024)],'structural')
        with self.assertRaisesRegex(ValueError,'2024 only'):m.calibrate([race(2025)],[1.])
        m.calibrate([race(2024)],[1.])
        self.assertFalse(m.to_dict()['live_eligible'])
        with self.assertRaisesRegex(ValueError,'follow'):m.predict([race(2024)])

    def test_tree_json_has_identical_predictions(self):
        m=BoostedRaceModel().fit([race(index=i) for i in range(1,5)],'structural',trees=2,minimum_leaf=2)
        x=matrix([race()],'structural')[0];b=m.bin(x)
        for tree in m.trees:
            np.testing.assert_array_equal(tree_predict(tree,b),tree_predict(json.loads(json.dumps(tree)),b))
        artifact=json.loads(json.dumps(m.to_dict()))
        loaded=BoostedRaceModel.from_dict(artifact,allow_research=True)
        np.testing.assert_array_equal(m.predict([race(2024)]),loaded.predict([race(2024)]))
        with self.assertRaisesRegex(ValueError,'research-only'):
            BoostedRaceModel.from_dict(artifact)
        bad=copy.deepcopy(artifact);bad['edges'][0]=[2.,1.]
        with self.assertRaisesRegex(ValueError,'bin edges'):
            BoostedRaceModel.from_dict(bad,allow_research=True)
        january=copy.deepcopy(artifact);january['train_end']='2024-01-04T00:00:00+09:00'
        self.assertEqual(BoostedRaceModel.from_dict(january,allow_research=True).train_end,january['train_end'])

    def test_unknown_winning_payout_is_not_zero(self):
        r=race();r['rows'][0]['win_payout_100']=None
        s=decide(r,[.8,.1,.1],dict(mode='top_probability',odds_cap=10,threshold=0))
        self.assertFalse(s['fully_settled']);self.assertIsNone(s['payout_yen'])

    def test_zero_bets_have_no_interval_or_target(self):
        r=race();s=decide(r,[.6,.3,.1],dict(mode='maximum_ev',odds_cap=10,threshold=9))
        self.assertEqual(s['stake_yen'],0);self.assertIsNone(interval([r],[s]))

    def test_policy_selection_rejects_evaluation_year(self):
        with self.assertRaisesRegex(ValueError,'2024 only'):select_policy([race(2025)],{'structural':[[.8,.1,.1]]})

    def test_invalid_probabilities_and_policy_rejected(self):
        p=dict(mode='maximum_ev',odds_cap=10,threshold=1.05)
        for bad in ([.5,.3],[-.2,.6,.6],[float('nan'),.5,.5]):
            with self.assertRaises(ValueError):decide(race(),bad,p)
        with self.assertRaises(ValueError):decide(race(),[.8,.1,.1],{**p,'odds_cap':-1})


if __name__ == '__main__':unittest.main()
