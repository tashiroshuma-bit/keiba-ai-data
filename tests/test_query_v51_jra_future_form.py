import unittest,json,sqlite3
from pathlib import Path
from scripts.query_v51_jra_future_form import select,DEFAULT

class OfficialFutureFormLookupTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with sqlite3.connect(f"file:{DEFAULT.resolve()}?mode=ro",uri=True) as con:
            cls.sample=con.execute(
                "SELECT horse_id,horse_name,verified_available_at FROM future_horse_form LIMIT 1").fetchone()
    def test_historical_nov8_asof_is_rejected_from_feature_use(self):
        hid,name,observed=self.sample
        cards=[{"number":k+1,"name":name if k==0 else "unknown"+str(k),
                "horse_id":hid if k==0 else None} for k in range(3)]
        response=select("fictional","2026-11-08T08:00:00+09:00",cards)
        self.assertEqual(response["source_backed_horses"],0)
        self.assertEqual(response["horses"][0]["status"],"OBSERVED_AFTER_FORECAST_CUTOFF")
        self.assertFalse(response["full_v51_34_feature_evidence_ready"])
    def test_future_time_is_allowed_if_exact_horse_id_and_name(self):
        hid,name,observed=self.sample
        horses=[{"number":1,"name":name,"horse_id":hid},
                {"number":2,"name":"unknown2","horse_id":None},
                {"number":3,"name":"unknown3","horse_id":None}]
        response=select("future","2030-01-01T08:00:00+09:00",horses)
        self.assertEqual(response["source_backed_horses"],1)
        self.assertEqual(response["horses"][0]["status"],"OBSERVED_BEFORE_ASOF")
        self.assertGreaterEqual(response["horses"][0]["features"]["prior_runs"],0)
        self.assertFalse(response["complete_form_coverage"])
    def test_wrong_name_is_not_linked(self):
        hid,name,observed=self.sample
        horses=[{"number":1,"name":"WRONG","horse_id":hid},
                {"number":2,"name":"unknown2","horse_id":None},
                {"number":3,"name":"unknown3","horse_id":None}]
        with self.assertRaises(ValueError):
            select("future","2030-01-01T08:00:00+09:00",horses)
    def test_invalid_naive_asof_fails(self):
        with self.assertRaises(ValueError):
            select("future","2030-01-01T08:00:00",[
                {"number":1,"name":"a","horse_id":None},
                {"number":2,"name":"b","horse_id":None},
                {"number":3,"name":"c","horse_id":None}])
if __name__=="__main__":unittest.main()
