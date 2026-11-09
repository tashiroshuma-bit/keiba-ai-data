import unittest
from scripts.v51_calibration_audit import metrics
ASOF="2026-11-14T09:00:00+09:00"
OFF="2026-11-14T10:00:00+09:00"
RACE="2026-11-14 Tokyo 1R"

def example():
    a={"schema":"jra-v50-weight-paired-preoff-v1","forecast_asof":ASOF,
        "races":[{"race":RACE,"original_off_at":OFF,
          "horses":[{"number":i,"v50_p1":p,
                      "weight_observed_at":ASOF,
                      "weight_change_bucket":bucket}
                    for i,p,bucket in [(1,.5,"-3..+3"),
                                       (2,.3,"+4..+9"),
                                       (3,.2,"unknown")]]}]}
    r={"observed_at":"2026-11-14T12:00:00+09:00",
       "races":[{"race":RACE,"finish_order":[1,3,2]}]}
    return a,r

class CalibrationTests(unittest.TestCase):
    def test_same_cohort_reliability(self):
        a,r=example();out=metrics(a,r)
        self.assertEqual(out["comparisons"]["v50"]["n_races"],1)
        self.assertEqual(out["comparisons"]["v51_shadow"]["n_races"],1)
        self.assertGreaterEqual(out["comparisons"]["v50"]["top1_ece_descriptive"],0)
        self.assertEqual(out["status"],"PROSPECTIVE_CALIBRATION_AUDIT_ONLY")
    def test_off_order(self):
        a,r=example();r["observed_at"]=ASOF
        with self.assertRaises(ValueError):metrics(a,r)
    def test_incomplete(self):
        a,r=example();r["races"][0]["finish_order"]=[1,2]
        with self.assertRaises(ValueError):metrics(a,r)
if __name__=="__main__":unittest.main()
