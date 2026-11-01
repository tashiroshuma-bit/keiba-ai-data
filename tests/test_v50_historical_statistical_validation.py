import unittest
from scripts.v50_historical_statistical_validation import report

def row(year, i, v50=(.6,.25,.15)):
    return {"race_id":f"{year}-{i}","date":f"{year}-01-{i%28+1:02d}",
    "partition":"calibration" if year=="2025" else "test","winner":1,
    "v49":{"1":.5,"2":.3,"3":.2},
    "v50":{"1":v50[0],"2":v50[1],"3":v50[2]}}

class StatisticalTest(unittest.TestCase):
    def test_separate_years(self):
        r=report([row("2025",i) for i in range(4)]+[row("2026",i) for i in range(4)])
        self.assertEqual(r["calibration_races"],4)
        self.assertEqual(r["test_races"],4)
        self.assertTrue(r["v50_2026"]["log_loss"] < r["v49_2026"]["log_loss"])
        self.assertFalse(r["production_promoted"])
    def test_rejects_duplicated_races(self):
        with self.assertRaises(ValueError):report([row("2025",0),row("2025",0),row("2026",0)])
    def test_rejects_year_leakage(self):
        bad=row("2026",1);bad["partition"]="calibration"
        with self.assertRaises(ValueError):report([row("2025",0),bad,row("2026",0)])
    def test_rejects_inconsistent_fields(self):
        bad=row("2026",0);bad["v50"]={"1":.6,"2":.4}
        with self.assertRaises(ValueError):report([row("2025",0),bad])
if __name__=="__main__":unittest.main()
