import unittest,tempfile,csv,os
from backtest_engine import analyze,run
class Tests(unittest.TestCase):
 def rows(self):
  return [dict(race_id='TEST',race_date='2025-10-19',horse_number=str(i+1),horse_name=f'H{i}',finish_position=str(i+1),pre_off_odds=str([2,4,8,16][i]),odds_timestamp='2025-10-19T15:35:00+09:00',off_timestamp='2025-10-19T15:40:00+09:00',final_win_odds='2.1') for i in range(4)]
 def test_probabilities(self):
  x=analyze(self.rows());self.assertAlmostEqual(x['p_win_sum'],1);self.assertTrue(all(abs(v-1)<1e-9 for v in x['p_rank_sums']));self.assertAlmostEqual(x['pair_probability_sum'],3);self.assertAlmostEqual(x['triple_probability_sum'],1)
 def test_postoff(self):
  r=self.rows();r[0]['odds_timestamp']='2025-10-19T15:41:00+09:00'
  with self.assertRaisesRegex(ValueError,'Post-off'):analyze(r)
 def test_no_fake_payout(self):
  r=self.rows();r[0]['final_win_odds']='';self.assertIsNone(analyze(r)['payout_yen'])
 def test_no_odds(self):
  r=self.rows();r[0]['pre_off_odds']=''
  with self.assertRaisesRegex(ValueError,'Missing'):analyze(r)
if __name__=='__main__':unittest.main()
