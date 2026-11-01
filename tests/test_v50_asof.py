import sqlite3
import tempfile
import unittest
from pathlib import Path
from scripts.build_v50_rider_residuals import build

class TestAsOfRiderResiduals(unittest.TestCase):
    def test_future_results_excluded(self):
        with tempfile.TemporaryDirectory() as d:
            db=Path(d)/"sample.sqlite"
            con=sqlite3.connect(db)
            con.execute("CREATE TABLE annual_report_races(race_id TEXT,race_date TEXT,surface TEXT,status TEXT,expected_runners INTEGER)")
            con.execute("CREATE TABLE annual_report_runners(race_id TEXT,horse_number INTEGER,horse_id TEXT,jockey_id TEXT,finish_order INTEGER)")
            for date in ("2026-10-20","2026-10-31"):
                race=date
                con.execute("INSERT INTO annual_report_races VALUES (?,?,?,?,?)",(race,date,"turf","validated_result",3))
                for n in range(1,4):
                    con.execute("INSERT INTO annual_report_runners VALUES (?,?,?,?,?)",(race,n,"h"+str(n),"j"+str(n),n))
            con.commit()
            con.close()
            result=build(db,"2026-11-01T09:00:00+09:00")
            self.assertEqual(result["races_used"],1)
            self.assertEqual(result["cutoff_date_exclusive"],"2026-10-30")
            self.assertIn("turf:j1",result["residuals"])

if __name__=="__main__":
    unittest.main()
