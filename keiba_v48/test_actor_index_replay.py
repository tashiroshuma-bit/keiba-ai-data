import copy
import unittest
import json
import numpy as np
from actor_indices import ActorIndices
from actor_index_replay import ActorReplay,index_picks
from test_actor_indices import field


class ActorReplayTests(unittest.TestCase):
    def test_warm_replay_matches_cold_asof_reference(self):
        history=[]
        for day in range(1,8):
            rows=field(f'r{day}',day)
            for i,r in enumerate(rows):r['jockey_id']=f'jra:j{(i+day)%4}'
            history+=rows
        replay=ActorReplay(history)
        for day in (2,4,8):
            cutoff=f'2024-01-{day:02d}T00:00:00+09:00'
            replay.fit_before(cutoff);reference=ActorIndices(history,cutoff)
            h,j,hn,jn=replay.scores(history[:4])
            for i,row in enumerate(history[:4]):
                for kind,values,counts in [('horse',h,hn),('jockey',j,jn)]:
                    expected=reference.entity(kind,row[kind+'_id'])
                    self.assertEqual(counts[i],expected['adjusted_starts'])
                    np.testing.assert_allclose(values[i],[expected['adjusted_indices'][key] for key in ('finish_performance','win_share','top2_share','top3_share')],atol=1e-7)
        with self.assertRaises(ValueError):replay.fit_before('2024-01-01T00:00:00+09:00')

    def test_future_outcomes_do_not_change_earlier_scores(self):
        history=field()+field('future',8);poison=copy.deepcopy(history)
        for r in poison[4:]:r['finish_position']=5-int(r['horse_number'])
        a,b=ActorReplay(history),ActorReplay(poison)
        for r in (a,b):r.fit_before('2024-01-03T00:00:00+09:00')
        np.testing.assert_array_equal(a.scores(history[:4])[0],b.scores(history[:4])[0])
        self.assertEqual(a.snapshot['source_race_ids_sha256'],b.snapshot['source_race_ids_sha256'])

    def test_explicit_tie_rule_and_distinct_prediction_tasks(self):
        result=index_picks([8,2,5,1],np.full((4,4),50.))
        self.assertEqual(result['winner_pick'],1)
        self.assertEqual(result['ordered_pick'],[1,2,5])
        self.assertTrue(result['tied_top1'])
        self.assertIsInstance(json.loads(json.dumps(result))['tied_top1'],bool)
        values=np.array([[99,1,0,0],[90,99,0,0],[80,1,0,99],[1,1,0,90]])
        result=index_picks([1,2,3,4],values)
        self.assertEqual(result['winner_pick'],2)
        self.assertEqual(result['ordered_pick'],[1,2,3])
        self.assertEqual(result['top3_pick'][:2],[3,4])


if __name__=='__main__':unittest.main()
