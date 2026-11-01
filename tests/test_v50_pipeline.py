"""End-to-end synthetic fixture test: SQLite -> as-of residuals -> v50 forecast."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from scripts.build_v50_rider_residuals import build
from scripts.run_v50_preoff import run

class TestV50Pipeline(unittest.TestCase):
    def test_database_to_forecast(self):
        with tempfile.TemporaryDirectory() as d:
            d=Path(d);db=d/"history.sqlite"
            con=sqlite3.connect(db)
            con.execute("CREATE TABLE annual_report_races(race_id TEXT,race_date TEXT,surface TEXT,status TEXT,expected_runners INTEGER)")
            con.execute("CREATE TABLE annual_report_runners(race_id TEXT,horse_number INTEGER,horse_id TEXT,jockey_id TEXT,finish_order INTEGER)")
            for date in ("2026-10-20","2026-10-21","2026-10-31"):
                con.execute("INSERT INTO annual_report_races VALUES (?,?,?,?,?)",(date,date,"turf","validated_result",3))
                for n in range(1,4):
                    con.execute("INSERT INTO annual_report_runners VALUES (?,?,?,?,?)",(date,n,"horse"+str(n),"jra:"+str(n),n))
            con.commit();con.close()
            snapshot=build(db,"2026-11-01T09:00:00+09:00")
            self.assertEqual(snapshot["races_used"],2)
            forecast={"asof":"2026-11-01T09:00:00+09:00",
                      "races":[{"race":"test-race","surface":"turf","horses":[
                      {"number":n,"name":"horse"+str(n),"jockey_id":"jra:"+str(n),"p1":p}
                      for n,p in ((1,.5),(2,.3),(3,.2))]}]}
            f=d/"forecast.json";r=d/"riders.json"
            f.write_text(json.dumps(forecast));r.write_text(json.dumps(snapshot))
            result=run(f,r)
            self.assertEqual(result["version"],"v50")
            self.assertEqual(result["races"][0]["rider_coverage"],3)
            horses=result["races"][0]["v50"]["horses"]
            self.assertAlmostEqual(sum(h["p1"] for h in horses),1.0)
            self.assertAlmostEqual(sum(h["p2"] for h in horses),1.0)
            self.assertAlmostEqual(sum(h["p3"] for h in horses),1.0)
            self.assertEqual(len(result["races"][0]["v49_p1"]),3)

if __name__=="__main__":
    unittest.main()
