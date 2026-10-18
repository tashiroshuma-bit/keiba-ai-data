import unittest,datetime as dt
from production_pipeline import validate,historical_features
BASE=dict(race_id='20250101-11',race_date='2025-01-01',off_timestamp='2025-01-01T15:40:00+09:00',horse_id='H1',horse_number='1',jockey_id='J1',odds_timestamp='2025-01-01T15:30:00+09:00',pre_off_odds='3.2',source_url='https://www.jra.go.jp/',finish_position='1',distance_m='2000',surface='芝')
class Tests(unittest.TestCase):
 def make(self):return [{**BASE,'horse_id':f'H{i}','horse_number':str(i),'jockey_id':f'J{i}','finish_position':str(i)} for i in range(1,4)]
 def test_valid(self):self.assertEqual(validate(self.make()),[])
 def test_cutoff(self):
  x=self.make();x[0]['odds_timestamp']='2025-01-01T15:39:00+09:00';self.assertTrue(validate(x))
 def test_missing_id(self):
  x=self.make();x[0]['horse_id']='';self.assertTrue(validate(x))
 def test_no_future_leak(self):
  x=self.make();y={**x[0],'race_id':'20250102-11','race_date':'2025-01-02','off_timestamp':'2025-01-02T15:40:00+09:00','finish_position':'3'}
  out=historical_features([y,*x]);self.assertEqual(out[0]['prior_4_starts'],0);self.assertEqual(out[-1]['prior_4_starts'],1)
if __name__=='__main__':unittest.main()
