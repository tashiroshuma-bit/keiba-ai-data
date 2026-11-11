import datetime as dt
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
from v51_recovered_id_conditional_rank import make_race_probabilities,softmax,calibrate,stage_ce,fit_conditional_stage
from v51_v50_same_asof_shadow import forecast, postrace,EXPECTED_DB

ASOF='2026-11-14T08:00:00+09:00'
OFF='2026-11-14T10:00:00+09:00'

def evidence(i):
    return {'horse_number':i,'horse_id':f'jra:202310000{i}',
            'source_url':'https://www.jra.go.jp/JRADB/accessU.html?CNAME=proof',
            'source_sha256':'a'*64,'observed_at':'2026-11-13T12:00:00+09:00'}

def model():
    return {'schema':'jra-v51-recovered-id-learned-conditional-rank-research-v1',
      'mode':'full','production_enabled':False,'canonical_db_sha256':EXPECTED_DB,
      'feature_names':[f'f{i}' for i in range(31)],'feature_mean':[0.0]*31,
      'feature_scale':[1.0]*31,'stage_coefficients':[[1.0]+[0.0]*30,
                [0.0,1.0]+[0.0]*29,[0.0,0.0,1.0]+[0.0]*28],
      'calibration':{'global_stage_temperatures':{'1':1.1,'2':1.2,'3':1.3},
       'winner_entropy_confidence_groups':{a+'__'+b:{'temp':1.1}
        for a in ('high_entropy','other_entropy') for b in ('close_field','clear_favorite')}}}

def manifests():
    v50={'version':'v50','standard_forecast':True,'canonical_database_sha256':EXPECTED_DB,
        'forecast_sha256':'b'*64,'forecast_asof':ASOF,
        'races':[{'race':'2026-11-14-Tokyo-1','v50':{'horses':[
            {'number':i,'name':f'H{i}','p1':p} for i,p in ((1,.5),(2,.3),(3,.2))]}}]}
    feats={'schema':'jra-v51-same-asof-full-field-features-v1',
        'source_A_sha256':'b'*64,'canonical_database_sha256':EXPECTED_DB,
        'forecast_asof':ASOF,'races':[{'race':'2026-11-14-Tokyo-1',
             'race_off_at':OFF,'features_generated_at':'2026-11-14T07:59:00+09:00',
             'horses':[{'number':i,'name':f'H{i}','horse_id':f'jra:202310000{i}',
                 'official_identity_proof':evidence(i),
                 'latest_history_date':'2026-11-13',
                 'features_observed_at':'2026-11-14T07:59:00+09:00',
                 'feature_values':[float(i),float(4-i),float(i)] + [0.0]*28}
                 for i in (1,2,3)]}]}
    return v50,feats

class RecoveredIDConditionalRanking(unittest.TestCase):
    def test_learned_first_second_third_joint_probabilities(self):
        z=[np.array([2.,1.,0.]),np.array([0.,1.,2.]),np.array([1.,2.,0.])]
        got=make_race_probabilities(z,model()['calibration'])
        for k in ('p1','p2','p3'):
            self.assertAlmostEqual(float(got[k].sum()),1.0,places=11)
        self.assertAlmostEqual(float(got['top3_sum'].sum()),3.0,places=11)
        self.assertEqual(len(set(got['ordered_pick'])),3)
        self.assertEqual(len(set(got['unordered_pick'])),3)
        self.assertGreater(got['ordered_pick_probability'],0)

    def test_identical_frozen_asof_and_horse_ids(self):
        base,features=manifests()
        got=forecast(base,features,model())
        self.assertEqual(len(got['races']),1)
        self.assertTrue(got['models_share_same_asof'])
        self.assertEqual(got['races'][0]['runners'][0]['v50_p1'],.5)
        self.assertFalse(got['v51_promoted'])
        res={'observed_at':'2026-11-14T12:00:00+09:00',
             'races':[{'race':'2026-11-14-Tokyo-1','finish_order':[1,3,2]}]}
        post=postrace(got,res)
        self.assertEqual(post['n_races'],1)
        self.assertEqual(post['metrics']['v50']['winner_hit'],1)
        self.assertIn('calibration_by_band',post['metrics']['v51'])

    def test_future_observation_and_mismatched_rosters_refused(self):
        base,features=manifests()
        features['races'][0]['horses'][0]['features_observed_at']='2026-11-14T11:00:00+09:00'
        with self.assertRaisesRegex(ValueError,'after v50 original asof'):
            forecast(base,features,model())
        base,features=manifests()
        features['races'][0]['horses'][0]['horse_id']='jra:2023109999'
        with self.assertRaisesRegex(ValueError,'horse ID evidence'):
            forecast(base,features,model())
        base,features=manifests()
        features['source_A_sha256']='c'*64
        with self.assertRaisesRegex(ValueError,'exact source'):
            forecast(base,features,model())
        base,features=manifests()
        features['races'][0]['horses'][0]['latest_history_date']='2026-11-14'
        with self.assertRaisesRegex(ValueError,'same-day'):
            forecast(base,features,model())
        base,features=manifests()
        features['races'][0]['horses'][0]['number']=99
        with self.assertRaisesRegex(ValueError,'field mismatch'):
            forecast(base,features,model())

    def test_after_off_and_missing_official_results_are_refused(self):
        base,features=manifests()
        features['races'][0]['race_off_at']='2026-11-14T07:00:00+09:00'
        with self.assertRaisesRegex(ValueError,'after race off'):
            forecast(base,features,model())
        base,features=manifests()
        pred=forecast(base,features,model())
        with self.assertRaisesRegex(ValueError,'full horse roster'):
            postrace(pred,{'observed_at':'2026-11-14T12:00:00+09:00',
                 'races':[{'race':'2026-11-14-Tokyo-1','finish_order':[1,3]}]})

    def test_immutable_write(self):
        from v51_v50_same_asof_shadow import immutable_write
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'immutable.json'
            immutable_write(p,{'ok':True})
            with self.assertRaises(FileExistsError):immutable_write(p,{'ok':False})

if __name__=='__main__':unittest.main()