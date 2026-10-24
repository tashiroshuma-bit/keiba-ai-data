import copy,datetime as dt,unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from v43_two_stage import prepare,revise
class TwoStageTests(unittest.TestCase):
 def setUp(self):
  self.card={'race_id':'test-race','off_timestamp':'2026-10-25T15:40:00+09:00','runners':[{'horse_number':1,'horse_name':'A'},{'horse_number':2,'horse_name':'B'},{'horse_number':3,'horse_name':'C'}]}
  self.status={'asof':'2026-10-24T17:00:00+09:00','rows':[[1],[2],[3]]}
  self.base=prepare(self.card,self.status)
  self.day={'race_id':'test-race','observed_at':'2026-10-25T14:00:00+09:00','received_at':'2026-10-25T14:01:00+09:00','source_url':'https://example.org/official','runners':[dict(horse_number=i,horse_name=n,jockey_id='j:'+str(i),carried_weight=57,gate=i,going='良',track='京都',surface='芝',distance_m=3000) for i,n in [(1,'A'),(2,'B'),(3,'C')]]}
 def test_prepared_and_revised(self):
  x=revise(self.base,self.day)
  self.assertEqual(x['prediction_status'],'READY_FOR_MODEL_RECOMPUTE')
  self.assertEqual(len(x['horses']),3)
  self.assertFalse(x['formal_eligible'])
  self.assertEqual(self.base['stage'],'PRE_RACE_BASELINE')
 def test_missing_day_field_fails_closed(self):
  d=copy.deepcopy(self.day);del d['runners'][0]['jockey_id']
  self.assertEqual(revise(self.base,d)['prediction_status'],'DAY_INPUT_INCOMPLETE')
 def test_incomplete_field_rejected(self):
  d=copy.deepcopy(self.day);d['runners'].pop()
  with self.assertRaisesRegex(ValueError,'INCOMPLETE_DAY_FIELD'):revise(self.base,d)
 def test_future_data_rejected(self):
  d=copy.deepcopy(self.day);d['received_at']='2026-10-25T15:36:00+09:00'
  with self.assertRaisesRegex(ValueError,'DAY_DATA_TOO_LATE'):revise(self.base,d)
 def test_wrong_race_rejected(self):
  d=copy.deepcopy(self.day);d['race_id']='wrong'
  with self.assertRaisesRegex(ValueError,'RACE_ID_MISMATCH'):revise(self.base,d)
 def test_tampered_baseline_rejected(self):
  b=copy.deepcopy(self.base);b['horses'][0]['cached_status']=[999]
  with self.assertRaisesRegex(ValueError,'BASELINE_TAMPERED'):revise(b,self.day)
 def test_wrong_name_rejected(self):
  d=copy.deepcopy(self.day);d['runners'][0]['horse_name']='Z'
  with self.assertRaisesRegex(ValueError,'HORSE_NAME_MISMATCH'):revise(self.base,d)
if __name__=='__main__':unittest.main()
