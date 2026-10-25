import copy
import json
import unittest
import datetime as dt
import tempfile
from pathlib import Path
from unittest.mock import patch
import numpy as np
from evidence_rank_model import EvidenceRankModel,evidence_matrix,replace_first,project_beta
from ranking_model import RankModel,augment,joint_distribution
from test_history_rank import race
from completion_validation import sha
from rank_forecast import forecast


class EvidenceRankTests(unittest.TestCase):
    def test_future_forecast_uses_same_probability_model(self):
        base=RankModel().fit([augment(race(i)) for i in range(4)],iterations=5)
        model=EvidenceRankModel(base,[-.2,.1,0,0,0,0],'2024-07-01T00:00:00+09:00')
        now=dt.datetime.now(dt.timezone.utc)
        rows=[dict(race_id='fixture',horse_id=f'jra:{i+1}',horse_number=str(i+1),jockey_id='jra:1',
            off_timestamp=(now+dt.timedelta(days=2)).isoformat(),features_asof=now.isoformat(),
            track='東京',surface='turf',distance_m=1600,sex_age='牡3',field_complete='yes',expected_runners=4,
            source_url='https://example.test/card') for i in range(4)]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);mp=root/'m.json';sp=root/'s.json';db=root/'db'
            mp.write_text(json.dumps(model.to_dict()));db.write_bytes(b'fixture')
            sp.write_text(json.dumps(dict(schema='keiba-evidence-rank-selection-v1',model_sha256=sha(mp),
                selection_end='2024-12-31T00:00:00+09:00',alpha=0,prediction_set_policy='exact_set')))
            with patch('rank_forecast.load_observed_enriched',return_value=[]):value=forecast(db,rows,mp,sp)
            p,_=model.predict(value['inputs']['features'])
            np.testing.assert_allclose(p[:,0],[r['p_first'] for r in value['runners']])
            self.assertEqual(value['allocation'],dict(bets=[],stake_yen=0))

    def test_first_replacement_keeps_conditional_podium_and_normalization(self):
        p,q=joint_distribution(np.array([[1,2,3,4],[4,3,2,1],[1,3,2,4]],float))
        first=np.array([.4,.3,.2,.1]);marginal,adjusted=replace_first(p,q,first)
        np.testing.assert_allclose(marginal[:,0],first)
        np.testing.assert_allclose(adjusted/first[:,None,None],q/p[:,0,None,None])
        np.testing.assert_allclose(marginal.sum(axis=0),1)
        self.assertTrue(np.all(marginal.sum(axis=1)<=1+1e-12))

    def test_2024_h1_fit_reload_and_temporal_restriction(self):
        base=RankModel().fit([augment(race(i)) for i in range(4)],iterations=5)
        cal=[augment(race(i,2024)) for i in range(4)]
        for r in cal:
            for j,f in enumerate(r['features']):f['history_starts']=j
        model=EvidenceRankModel.fit(base,cal,.1,iterations=10)
        restored=EvidenceRankModel.from_dict(json.loads(json.dumps(model.to_dict())))
        a,qa=model.predict(cal[0]['features'],False);b,qb=restored.predict(cal[0]['features'],False)
        np.testing.assert_array_equal(a,b);np.testing.assert_array_equal(qa,qb)
        with self.assertRaises(ValueError):restored.predict(cal[0]['features'])
        with self.assertRaises(ValueError):EvidenceRankModel.fit(base,[augment(race(1,2025))],.1)
        corrupt=model.to_dict();corrupt['live_eligible']=True
        with self.assertRaises(ValueError):EvidenceRankModel.from_dict(corrupt)

    def test_evidence_does_not_consume_outcomes_and_is_permutation_equivariant(self):
        fs=augment(race())['features']
        for i,f in enumerate(fs):f['history_starts']=i
        p=np.array([.4,.3,.2,.1]);x=evidence_matrix(fs,p)
        order=[3,1,0,2];np.testing.assert_allclose(evidence_matrix([fs[i] for i in order],p[order]),x[order])
        poisoned=copy.deepcopy(fs)
        for f in poisoned:f.update(finish_position=99,final_win_odds=999,payouts={'x':999})
        np.testing.assert_array_equal(evidence_matrix(poisoned,p),x)

    def test_coefficient_projection_preserves_positive_probability_direction(self):
        b=project_beta(np.array([-.9,0,0,5,-7,0]))
        c=[1+b[0],1+b[0]+b[4],1+b[0]+b[3]+b[4]]
        self.assertTrue(min(c)>=.25-1e-12 and max(c)<=2+1e-12)


if __name__=='__main__':unittest.main()
