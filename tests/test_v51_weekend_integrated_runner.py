import datetime as dt
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts.v51_weekend_integrated_runner import run

ASOF="2026-11-14T08:00:00+09:00"
OFF="2026-11-14T10:00:00+09:00"
RACE="2026-11-14 Tokyo 1R"
NOW=dt.datetime.fromisoformat("2026-11-14T08:01:00+09:00")

def write(path,obj):
    path.write_text(json.dumps(obj,ensure_ascii=False),encoding="utf8")
    return hashlib.sha256(path.read_bytes()).hexdigest()
def original():
    return {"source_model":"A","asof":ASOF,
       "races":[{"race":RACE,"original_off_at":OFF,
       "horses":[{"number":i,"name":f"H{i}"} for i in (1,2,3)]}]}

class V51WeekendIntegratedRunnerTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.source=self.root/"source_a.json"
        self.srcsha=write(self.source,original())
        self.db=self.root/"db.sqlite"
        self.db.write_bytes(b"synthetic TEST fixture only")
    def tearDown(self):self.tmp.cleanup()
    def mocked_standard(self,source,db,output):
        payload={"version":"v50","standard_forecast":True,"live_bet_generation":False,
            "forecast_sha256":self.srcsha,"rider_sha256":"f"*64,
            "canonical_database_sha256":"a"*64,"policy_sha256":"b"*64,
            "forecast_asof":ASOF,
            "races":[{"race":RACE,"v50":{"horses":[{"number":i,"name":f"H{i}","p1":p}
                for i,p in ((1,.5),(2,.3),(3,.2))]}}]}
        write(output,payload)
        return payload
    def test_morning_run_keeps_weights_missing(self):
        with patch("scripts.v51_weekend_integrated_runner.standard_forecast",self.mocked_standard):
            response=run(self.source,self.db,self.root/"morning",now=NOW)
        self.assertEqual(response["races"],1)
        self.assertEqual(response["weight_status"],"NOT_YET_PUBLISHED_OR_NOT_SUPPLIED")
        self.assertEqual(response["rank_status"],"NOT_SUPPLIED_NO_LEARNED_2ND_3RD")
        self.assertTrue(Path(response["manifest"]).exists())
    def test_later_complete_weight_capture(self):
        w={"asof":ASOF,"races":[{"race":RACE,"original_off_at":OFF,
            "observed_at":ASOF,"source_url":"https://example.org/synthetic",
            "source_sha256":None,"horses":[{"number":i,"body_weight_kg":480+i,
            "weight_change_kg":0,"weight_observed_at":ASOF} for i in (1,2,3)]}]}
        archive=self.root/"raw";archive.mkdir()
        original_bytes=b"SYNTHETIC RAW WEIGHT SOURCE"
        h=hashlib.sha256(original_bytes).hexdigest()
        (archive/(h+".bin")).write_bytes(original_bytes)
        w["races"][0]["source_sha256"]=h
        weights=self.root/"weights.json";write(weights,w)
        with patch("scripts.v51_weekend_integrated_runner.standard_forecast",self.mocked_standard):
            out=run(self.source,self.db,self.root/"afternoon",weights=weights,
                    weight_archive=archive,now=NOW)
        self.assertEqual(out["weight_status"],"FROZEN_PREOFF_SHADOW_ONLY")
        with patch("scripts.v51_weekend_integrated_runner.standard_forecast",self.mocked_standard):
            with self.assertRaises(FileExistsError):
                run(self.source,self.db,self.root/"afternoon",weights=weights,
                    weight_archive=archive,now=NOW)
    def test_raw_source_mismatch_refused(self):
        w={"asof":ASOF,"races":[{"race":RACE,"original_off_at":OFF,
            "observed_at":ASOF,"source_url":"https://example.org/synthetic",
            "source_sha256":"a"*64,"horses":[{"number":i,"body_weight_kg":481,
            "weight_change_kg":0,"weight_observed_at":ASOF} for i in (1,2,3)]}]}
        weights=self.root/"w.json";write(weights,w)
        (self.root/"raw").mkdir()
        with patch("scripts.v51_weekend_integrated_runner.standard_forecast",self.mocked_standard):
            with self.assertRaises(ValueError):
                run(self.source,self.db,self.root/"invalid",weights=weights,
                    weight_archive=self.root/"raw",now=NOW)
    def test_refuse_after_actual_off(self):
        with self.assertRaises(ValueError):
            run(self.source,self.db,self.root/"late",
              now=dt.datetime.fromisoformat("2026-11-14T10:01:00+09:00"))
    def test_refuse_future_reported_snapshot(self):
        with self.assertRaises(ValueError):
            run(self.source,self.db,self.root/"future",
              now=dt.datetime.fromisoformat("2026-11-14T07:59:00+09:00"))
    def test_same_asof_research_features_and_missing_ids(self):
        features={"races":[{"race":RACE,"asof":ASOF,"off":OFF,
            "track":"Tokyo","surface":"turf","distance_m":1600,
            "class_index":1,"runners":[{"number":i,"horse_id":None,"jockey_id":str(i),
                "identity_evidence":None} for i in (1,2,3)]}]}
        f=self.root/"research.json";write(f,features)
        with patch("scripts.v51_weekend_integrated_runner.standard_forecast",self.mocked_standard):
            output=run(self.source,self.db,self.root/"features",research_input=f,now=NOW)
        manifest=json.loads(Path(output["manifest"]).read_text())
        self.assertEqual(manifest["optional"]["features"]["races"][0]["identity_coverage"]["missing_ids"],3)
    def test_reject_unmatched_learned_rank(self):
        rank={"races":[{"race":RACE,"deployment_status":"experimental_rank_shadow",
            "strict_production_validated":False,"created_at":ASOF,"off_timestamp":OFF,
            "runners":[{"horse_number":i} for i in (1,2,4)]}]}
        p=self.root/"rank.json";write(p,rank)
        with patch("scripts.v51_weekend_integrated_runner.standard_forecast",self.mocked_standard):
            with self.assertRaises(ValueError):
                run(self.source,self.db,self.root/"wrong_rank",rank_snapshots=p,now=NOW)
if __name__=="__main__":unittest.main()
