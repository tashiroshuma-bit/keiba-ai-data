"""Synthetic-only adversarial tests, not a real JRA PDF validation."""
import copy
import unittest
from jra_v46_roster_crosscheck import crosscheck

URL = 'https://www.jra.go.jp/keiba/rpdf/pdf/20261025-04tokyo09.pdf'
OTHER = 'https://www.jra.go.jp/JRADB/accessD.html'
H = 'a' * 64

def sample():
    probe = {'status':'CANDIDATES_ONLY_UNVERIFIED', 'production_freeze_allowed':False,
             'source_url_claimed':URL, 'pdf_sha256':H,
             'observed_at_claimed':'2026-10-25T08:00:00+09:00',
             'races':[{'race_number_expected':n,'race_number_header_candidates':[n],
                       'post_time_candidate':'10:00','post_time_method':'direct','issues':[],
                       'runner_candidates':[{'horse_number_candidate':1,'horse_name_candidate':'テストホース','weight_candidate':55.0}]}
                      for n in range(1,13)]}
    roster = {'pdf_url':URL,'pdf_sha256':H,'race_date':'20261025',
              'independent_roster_url':OTHER,'independent_roster_sha256':'b'*64,
              'independent_roster_observed_at':'2026-10-25T08:05:00+09:00',
              'races':[{'race_number':n,'post_time':'10:00','runners':[{'number':1,'name':'テストホース','weight':55,'status':'running'}]} for n in range(1,13)]}
    return probe,roster

class CrosscheckTest(unittest.TestCase):
    def test_synthetic_consistency_does_not_unlock_freeze(self):
        p,r=sample(); out=crosscheck(p,r)
        self.assertTrue(out['candidate_consistency_pass'])
        self.assertEqual(out['matched_runner_rows'],12)
        self.assertFalse(out['source_authenticity_proven'])
        self.assertFalse(out['production_freeze_allowed'])
    def test_name_and_weight_mismatch(self):
        p,r=sample(); r['races'][0]['runners'][0]['name']='別馬'; r['races'][1]['runners'][0]['weight']=57
        out=crosscheck(p,r); self.assertFalse(out['candidate_consistency_pass'])
        self.assertTrue(any('name_disagrees' in x for x in out['issues']))
        self.assertTrue(any('weight_disagrees' in x for x in out['issues']))
    def test_duplicate_number_and_scratched(self):
        p,r=sample(); r['races'][0]['runners'].append(copy.deepcopy(r['races'][0]['runners'][0]))
        r['races'][1]['runners'][0]['status']='scratched'
        out=crosscheck(p,r); self.assertTrue(any('duplicate' in x for x in out['issues']))
        self.assertTrue(any('scratches' in x for x in out['issues']))
    def test_late_observation_and_ambiguous_time(self):
        p,r=sample(); p['observed_at_claimed']='2026-10-25T11:00:00+09:00'
        p['races'][0]['post_time_method']='reversed_glyph_order_unverified'
        out=crosscheck(p,r); self.assertTrue(any('not_preoff' in x for x in out['issues']))
        self.assertTrue(any('ambiguous' in x for x in out['issues']))
    def test_wrong_sha_or_same_roster_url(self):
        p,r=sample(); r['pdf_sha256']='c'*64; r['independent_roster_url']=URL
        out=crosscheck(p,r); self.assertTrue(any('sha_disagrees' in x for x in out['issues']))
        self.assertTrue(any('same' in x for x in out['issues']))
    def test_missing_race_and_naive_timestamp(self):
        p,r=sample(); p['races'].pop(); r['independent_roster_observed_at']='2026-10-25T08:05:00'
        out=crosscheck(p,r); self.assertTrue(any('twelve_races_required' in x for x in out['issues']))
        self.assertTrue(any('timestamp' in x for x in out['issues']))

if __name__ == '__main__':
    unittest.main()
