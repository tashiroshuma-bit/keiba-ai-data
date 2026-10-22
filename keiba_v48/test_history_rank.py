import copy
import json
import unittest
import numpy as np
from features import HistoryIndex
from ranking_model import RankModel,augment
from history_rank_model import HistoryRankModel,augment_history,NAMES
from history_blend_model import HistoryBlendModel,augment_blend
from test_ranking import race as base_race


def race(*args,**kwargs):
    r=base_race(*args,**kwargs)
    for row,feature in zip(r['rows'],r['features']):row['horse_id']=feature['horse_id']
    return r


class HistoryRankTests(unittest.TestCase):
    def test_only_observable_prior_starts_enter_features(self):
        r=race(5,2024)
        def start(rid,off,available):
            return dict(race_id=rid,horse_id='jra:1',jockey_id='jra:1',off_timestamp=off,result_available_at=available,
                        source_url='https://example.test/result',distance_m=1600,surface='turf',finish_position=1)
        idx=HistoryIndex([start('prior','2023-01-01T12:00:00+09:00','2023-01-03T00:00:00+09:00'),
            start('late','2023-12-31T12:00:00+09:00','2024-01-07T00:00:00+09:00'),
            start(r['race_id'],r['off_timestamp'],'2024-01-07T00:00:00+09:00')])
        result=augment_history(r,idx)
        self.assertAlmostEqual(result['features'][0]['values'][-6],2/11)
        self.assertAlmostEqual(result['features'][1]['values'][-6],.1)
        self.assertEqual(len(result['features'][0]['values']),len(NAMES))

    def test_target_outcomes_and_quotes_do_not_enter_features(self):
        a=race();b=copy.deepcopy(a)
        for row in b['rows']:row.update(finish_position=99,final_win_odds=999,payouts={'win:1':999})
        idx=HistoryIndex([])
        self.assertEqual([f['values'] for f in augment_history(a,idx)['features']],
                         [f['values'] for f in augment_history(b,idx)['features']])
        a['rows'][0]['sex_age']='(cid:141)3鹿'
        self.assertEqual(augment_history(a,idx)['features'][0]['values'][23],3)

    def test_reload_and_temporal_boundary(self):
        idx=HistoryIndex([]);rs=[augment_history(race(i),idx) for i in range(4)]
        m=HistoryRankModel().fit(rs,iterations=10);restored=HistoryRankModel.from_dict(json.loads(json.dumps(m.to_dict())))
        np.testing.assert_array_equal(m.predict(rs[0]['features'],enforce_time=False)[0],restored.predict(rs[0]['features'],enforce_time=False)[0])
        with self.assertRaises(ValueError):restored.predict(rs[0]['features'])
        with self.assertRaises(ValueError):HistoryRankModel().fit([augment_history(race(year=2025),idx)])

    def test_joint_blend_coherence_and_component_contracts(self):
        idx=HistoryIndex([]);rs=[race(i) for i in range(4)]
        base=RankModel().fit([augment(r) for r in rs],iterations=10)
        specialist=HistoryRankModel().fit([augment_blend(r,idx) for r in rs],iterations=10)
        fs=augment_blend(rs[0],idx)['features']
        for w in (0,.25,1):
            m=HistoryBlendModel(base,specialist,w,.1,.3);restored=HistoryBlendModel.from_dict(m.to_dict())
            p,q=m.predict(fs,enforce_time=False)
            np.testing.assert_array_equal(p,restored.predict(fs,enforce_time=False)[0])
            np.testing.assert_allclose(p.sum(axis=0),1);np.testing.assert_allclose(p[:,0],q.sum(axis=(1,2)))
            self.assertTrue(np.all(p.sum(axis=1)<=1+1e-12));self.assertAlmostEqual(float(q.sum()),1)
        with self.assertRaises(ValueError):HistoryBlendModel(base,specialist,1.5)


if __name__=='__main__':unittest.main()
