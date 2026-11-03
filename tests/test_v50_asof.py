import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path
from scripts.build_v50_rider_residuals import build, file_sha256, open_canonical_readonly

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


    def test_canonical_db_is_opened_read_only(self):
        with tempfile.TemporaryDirectory() as d:
            db=Path(d)/"canonical with spaces.sqlite"
            con=sqlite3.connect(db)
            con.execute("CREATE TABLE guard(value INTEGER)")
            con.execute("INSERT INTO guard VALUES(1)")
            con.commit()
            con.close()
            before=hashlib.sha256(db.read_bytes()).hexdigest()
            ro=open_canonical_readonly(db)
            try:
                self.assertEqual(ro.execute("PRAGMA query_only").fetchone()[0],1)
                self.assertEqual(ro.execute("SELECT value FROM guard").fetchone()[0],1)
                with self.assertRaises(sqlite3.OperationalError):
                    ro.execute("INSERT INTO guard VALUES(2)")
            finally:
                ro.close()
            self.assertEqual(hashlib.sha256(db.read_bytes()).hexdigest(),before)

    def test_missing_canonical_db_is_not_created(self):
        with tempfile.TemporaryDirectory() as d:
            db=Path(d)/"missing.sqlite"
            with self.assertRaises(sqlite3.OperationalError):
                build(db,"2026-11-01T09:00:00+09:00")
            self.assertFalse(db.exists())

    def test_large_file_sha256_is_streamed_correctly(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"sample.bin"
            content=(b"v50-canonical-integrity-"*70000)
            path.write_bytes(content)
            self.assertEqual(file_sha256(path),hashlib.sha256(content).hexdigest())

if __name__=="__main__":
    unittest.main()
