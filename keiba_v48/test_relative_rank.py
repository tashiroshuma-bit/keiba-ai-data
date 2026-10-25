import copy
import json
import unittest
import datetime as dt
import tempfile
from pathlib import Path
from unittest.mock import patch
import numpy as np
from features import HistoryIndex
from ranking_model import RankModel,augment
from relative_rank_model import (relative_values,augment_relative,matrix,RelativeRankTree,
                                 RelativeRankBlend,NAMES,HISTORY_NAMES)
from test_history_rank import race
from completion_validation import sha
from rank_forecast import forecast


def prepared(i=0,year=2023):
    r=race(i,year)
    for row in r['rows']:row.update(distance_m=1600,surface='turf',class_level=0)
    return augment_relative(r,HistoryIndex([]))


class RelativeRankTests(unittest.TestCase):
    def test_future_entrypoint_uses_identical_reloaded_model_and_rejects_proxy(self):
        rs=[prepared(i) for i in range(4)]
        base=RankModel().fit([augment(race(i)) for i in range(4)],iterations=5)
        specialist=RelativeRankTree().fit(rs,'win',trees=2,minimum_leaf=2)
        model=RelativeRankBlend(base,specialist,.25)
        now=dt.datetime.now(dt.timezone.utc)
        rows=[dict(race_id='future',horse_number=str(i+1),horse_id=f'jra:{i+1}',jockey_id='jra:1',
            track='東京',surface='turf',distance_m=1600,sex_age='牡3',field_complete='yes',expected_runners=4,
            off_timestamp=(now+dt.timedelta(days=2)).isoformat(),features_asof=now.isoformat(),
            feature_generation_mode='observed_history',source_url='https://example.test/card') for i in range(4)]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);m=root/'model.json';s=root/'selection.json';db=root/'db'
            m.write_text(json.dumps(model.to_dict()));db.write_bytes(b'fixture')
            s.write_text(json.dumps(dict(schema='keiba-relative-rank-selection-v1',model_sha256=sha(m),
                selection_end='2024-12-31T00:00:00+09:00',alpha=0,prediction_set_policy='exact_set')))
            with patch('rank_forecast.load_observed_enriched',return_value=[]):
                result=forecast(db,rows,m,s)
                p,_=model.predict_races([dict(rows=rows,features=result['inputs']['features'])])[0]
                np.testing.assert_allclose(p[:,0],[r['p_first'] for r in result['runners']])
                self.assertEqual(result['allocation'],dict(bets=[],stake_yen=0))
                rows[0]['feature_generation_mode']='CAREER_TOTALS_PROXY'
                with self.assertRaises(ValueError):forecast(db,rows,m,s)

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
