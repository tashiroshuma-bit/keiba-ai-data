"""Official v51 route is independent of v50 and strictly point-in-time."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts.standard_v51_forecast import forecast

DB="5d16777588420ac88bab5df21defb85d9346c2b918bb71859af06893752bcadd"
ASOF="2026-11-14T08:00:00+09:00"
EARLY="2026-11-14T07:00:00+09:00"
OFF="2026-11-14T10:00:00+09:00"

def fixture():
    state={"database":{"sha256":DB},"standard_forecast":{
        "version":"v51","adopted_by_user":True,
        "policy":"operations/prediction_policy/standard_v51.json",
        "entrypoint":"scripts/standard_v51_forecast.py"}}
    policy={"standard_version":"v51","standard_for_future_races":True,
            "v50_fallback":False,"live_bet_generation":False,
            "expected_canonical_db_sha256":DB,
            "requires_feature_schema":"jra-v51-preoff-feature-snapshot-v1"}
    groups={a+"__"+b:{"temp":1.0} for a in ("high_entropy","other_entropy")
            for b in ("close_field","clear_favorite")}
    model={"production_enabled":True,"mode":"full","feature_count":31,
           "canonical_db_sha256":DB,
           "feature_mean":[0]*31,"feature_scale":[1]*31,
           "stage_coefficients":[[1.0]+[0.0]*30,[0.0,1.0]+[0.0]*29,[0.0,0.0,1.0]+[0.0]*28],
           "calibration":{"group_entropy_cutoff":0.94,"group_favorite_cutoff":0.25,
              "global_stage_temperatures":{"1":1.0,"2":1.0,"3":1.0},
              "winner_entropy_confidence_groups":groups}}
    horses=[]
    for i in (1,2,3):
        horses.append({"number":i,"name":f"H{i}","horse_id":f"jra:202310000{i}",
             "official_identity_proof":{"horse_number":i,"horse_id":f"jra:202310000{i}",
                  "source_url":"https://www.jra.go.jp/JRADB/example",
                  "source_sha256":"a"*64,"observed_at":EARLY},
             "features_observed_at":EARLY,"prior_starts":0,"latest_history_date":None,
             "feature_values":[float(i),float(4-i),float(i)]+[0.0]*28})
    doc={"schema":"jra-v51-preoff-feature-snapshot-v1","canonical_database_sha256":DB,
         "roster_source_url":"https://www.jra.go.jp/race/example",
         "roster_source_sha256":"b"*64,"roster_captured_at":EARLY,
         "forecast_asof":ASOF,
         "races":[{"race":"2026-11-14-Tokyo-1","race_off_at":OFF,
                   "features_generated_at":EARLY,"horses":horses}]}
    return state,policy,model,doc

class OfficialV51Test(unittest.TestCase):
    def invoke(self,mutate=None):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            state,policy,model,doc=fixture()
            if mutate:mutate(state,policy,model,doc)
            for name,data in (("s.json",state),("p.json",policy),("m.json",model),("f.json",doc)):
                (root/name).write_text(json.dumps(data),encoding="utf-8")
            (root/"db.sqlite").write_bytes(b"sample")
            with patch("scripts.standard_v51_forecast.digest",return_value=DB):
                return forecast(root/"f.json",root/"db.sqlite",root/"out.json",
                  state_path=root/"s.json",policy_path=root/"p.json",model_path=root/"m.json")
    def test_v51_independent_rank_and_joint_normalization(self):
        p=self.invoke()
        self.assertEqual(p["version"],"v51")
        self.assertFalse(p["v50_used"])
        self.assertEqual(len(p["races"]),1)
        r=p["races"][0]
        self.assertAlmostEqual(sum(h["p1"] for h in r["runners"]),1)
        self.assertAlmostEqual(sum(h["p2"] for h in r["runners"]),1)
        self.assertAlmostEqual(sum(h["p3"] for h in r["runners"]),1)
        self.assertEqual(r["combination_audit"]["ordered_total"],6)
        self.assertEqual(r["combination_audit"]["unordered_total"],1)
        self.assertAlmostEqual(r["combination_audit"]["mass"],1)
    def test_refuse_v50_as_standard(self):
        with self.assertRaisesRegex(ValueError,"routing"):
            self.invoke(lambda s,p,m,f:s["standard_forecast"].update({"version":"v50"}))
    def test_refuse_post_asof_feature(self):
        with self.assertRaisesRegex(ValueError,"after prediction"):
            self.invoke(lambda s,p,m,f:f["races"][0]["horses"][0].update({
                "features_observed_at":"2026-11-14T09:00:00+09:00"}))
    def test_refuse_false_horse_identity(self):
        with self.assertRaisesRegex(ValueError,"evidence mismatch"):
            self.invoke(lambda s,p,m,f:f["races"][0]["horses"][0].update({"horse_id":"jra:fake"}))
    def test_refuse_missing_prior_source_proof(self):
        with self.assertRaisesRegex(ValueError,"historical source publication"):
            self.invoke(lambda s,p,m,f:f["races"][0]["horses"][0].update({
                "prior_starts":1,"latest_history_date":"2026-11-01"}))
    def test_refuse_postoff_snapshot(self):
        with self.assertRaisesRegex(ValueError,"race is not before off"):
            self.invoke(lambda s,p,m,f:f["races"][0].update({"race_off_at":"2026-11-14T07:00:00+09:00"}))
    def test_refuse_v50_fallback_policy(self):
        with self.assertRaisesRegex(ValueError,"official policy"):
            self.invoke(lambda s,p,m,f:p.update({"v50_fallback":True}))

if __name__=="__main__":unittest.main()
