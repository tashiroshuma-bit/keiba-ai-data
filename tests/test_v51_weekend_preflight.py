import json
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
if __name__=="__main__":unittest.main()
