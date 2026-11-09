import json
import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path
from scripts.v51_weekend_preflight import preflight

class WeekendPreflightTests(unittest.TestCase):
    def test_missing_real_dependencies_are_blockers(self):
        root=Path(__file__).resolve().parents[1]
        p=preflight(root)
        self.assertEqual(p["status"],"NOT_READY")
        self.assertFalse(p["checks"]["canonical_db_present"])
        self.assertFalse(p["checks"]["real_source_A_present"])
        self.assertEqual(p["production_model"],"v50")
    def test_wrong_database_is_refused(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/"jra_2023_2025.sqlite"
            f.write_bytes(b"NONCANONICAL-STUB")
            p=preflight(root,database=f)
            self.assertFalse(p["checks"]["canonical_db_sha_match"])
            self.assertFalse(p["checks"]["canonical_db_size_match"])
            self.assertEqual(p["status"],"NOT_READY")
    def test_missing_preoff_sources_not_silent(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as d:
            x=Path(d)/"source.json";x.write_text("{}")
            p=preflight(root,source_a=x)
            self.assertTrue(p["checks"]["real_source_A_present"])
            self.assertFalse(p["checks"]["weight_manifest_present"])
            self.assertIn("weight_source_bytes_dir_present",p["blockers"])

    def test_morning_ready_before_weight_announcement(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as d:
            base=Path(d)
            state=json.loads((root/"PROJECT_STATE.json").read_text())
            db=base/"small_valid.db"
            con=sqlite3.connect(db)
            con.execute("CREATE TABLE test(x INTEGER)")
            con.commit();con.close()
            state["database"]["bytes"]=db.stat().st_size
            state["database"]["sha256"]=hashlib.sha256(db.read_bytes()).hexdigest()
            (base/"PROJECT_STATE.json").write_text(json.dumps(state))
            from scripts.v51_weekend_preflight import NEEDED
            for name in NEEDED:
                p=base/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text("fixture only")
            source=base/"real_source_placeholder.json";source.write_text("{}")
            morning=preflight(base,database=db,source_a=source,phase="morning")
            final=preflight(base,database=db,source_a=source,phase="final")
            self.assertEqual(morning["status"],"READY_TO_ATTEMPT_REAL_PREOFF")
            self.assertTrue(morning["checks"]["canonical_db_integrity_ok"])
            self.assertEqual(final["status"],"NOT_READY")
            self.assertIn("weight_manifest_present",final["blockers"])
if __name__=="__main__":unittest.main()
