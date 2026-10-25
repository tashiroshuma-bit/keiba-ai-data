import copy
import json
import unittest
import numpy as np
from features import HistoryIndex
from ranking_model import RankModel,augment
from relative_rank_model import (relative_values,augment_relative,matrix,RelativeRankTree,
                                 RelativeRankBlend,NAMES,HISTORY_NAMES)
from test_history_rank import race


def prepared(i=0,year=2023):
    r=race(i,year)
    for row in r['rows']:row.update(distance_m=1600,surface='turf',class_level=0)
    return augment_relative(r,HistoryIndex([]))


class RelativeRankTests(unittest.TestCase):
    def test_equal_form_has_equal_percentile_and_permutation_equivariance(self):
        values=np.zeros((4,len(HISTORY_NAMES)));values[:,0]=[.2,.2,.4,.6]
        result=relative_values(values)
        self.assertEqual(result.shape,(4,len(NAMES)))
        self.assertAlmostEqual(result[0,len(HISTORY_NAMES)+1],.25)
        np.testing.assert_array_equal(result[0],result[1])
        order=[3,1,0,2]
        np.testing.assert_allclose(relative_values(values[order]),result[order])

    def test_target_outcomes_and_market_do_not_enter_features(self):
        r=race();s=copy.deepcopy(r)
        for group in (r,s):
            for row in group['rows']:row.update(distance_m=1600,surface='turf')
        for row in s['rows']:row.update(finish_position=99,final_win_odds=999,payouts={'win:1':999})
        a=augment_relative(r,HistoryIndex([]));b=augment_relative(s,HistoryIndex([]))
        np.testing.assert_array_equal(matrix([a]),matrix([b]))
        self.assertEqual(len(a['features'][0]['legacy_values']),29)

    def test_training_reload_coherence_and_time(self):
        rs=[prepared(i) for i in range(6)]
        base=RankModel().fit([augment(race(i)) for i in range(6)],iterations=8)
        for family in ('win','shared_top3','stagewise_top3'):
            m=RelativeRankTree().fit(rs,family,trees=3,minimum_leaf=2,regularization=1)
            blend=RelativeRankBlend(base,m,.25)
            restored=RelativeRankBlend.from_dict(json.loads(json.dumps(blend.to_dict())))
            for (a,qa),(b,qb) in zip(blend.predict_races(rs,False),restored.predict_races(rs,False)):
                np.testing.assert_array_equal(a,b);np.testing.assert_array_equal(qa,qb)
                np.testing.assert_allclose(a.sum(axis=0),1)
                self.assertAlmostEqual(qa.sum(),1)
                self.assertTrue(np.all(a.sum(axis=1)<=1+1e-12))
            with self.assertRaises(ValueError):restored.predict_races(rs)
        with self.assertRaises(ValueError):RelativeRankTree().fit([prepared(year=2025)],'win',trees=1)

    def test_corrupt_or_live_artifact_rejected(self):
        model=RelativeRankTree().fit([prepared(i) for i in range(3)],'win',trees=2,minimum_leaf=2)
        artifact=model.to_dict();artifact['live_eligible']=True
        with self.assertRaises(ValueError):RelativeRankTree.from_dict(artifact)
        artifact=model.to_dict();artifact['temperature']=float('nan')
        with self.assertRaises(ValueError):RelativeRankTree.from_dict(artifact)


if __name__=='__main__':unittest.main()
