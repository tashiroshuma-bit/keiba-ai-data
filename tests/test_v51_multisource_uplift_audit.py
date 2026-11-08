import tempfile,unittest,json,shutil,sqlite3
from pathlib import Path
from scripts.audit_v51_multisource_uplift import audit,write_report,DB,AUDIT

class MultiSourceUpliftAuditTests(unittest.TestCase):
    def test_actual_repo_overlay_has_no_new_horse_features(self):
        x=audit()
        self.assertEqual(x["counts"]["observations"],0)
        self.assertEqual(x["counts"]["preoff_usable_observations"],0)
        self.assertEqual(x["same_asof_frozen_v50_v51_pairs"],0)
        self.assertIsNone(x["observed_uplift"])
        self.assertFalse(x["model_upgraded"])
        self.assertEqual(x["standard_version"],"v50")
        self.assertEqual(x["official_results_paired"],34)
    def test_corrupt_copy_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            copy=Path(d)/"tampered.sqlite"
            shutil.copyfile(DB,copy)
            with copy.open("ab") as f:f.write(b"tamper")
            with self.assertRaises(ValueError):
                audit(db=copy)
    def test_no_model_ranking_modified(self):
        with tempfile.TemporaryDirectory() as d:
            x=audit()
            jsonpath=Path(d)/"result.json";markdown=Path(d)/"result.md"
            write_report(x,jsonpath,markdown)
            after=json.loads(jsonpath.read_text())
            self.assertFalse(after["model_upgraded"])
            self.assertIn("算定不能",markdown.read_text())
    def test_provenance_row_cannot_silently_change_cohort(self):
        with tempfile.TemporaryDirectory() as d:
            copy=Path(d)/"extra.sqlite"
            shutil.copyfile(DB,copy)
            c=sqlite3.connect(copy)
            c.execute("INSERT INTO multi_source_import_audit VALUES (?,?,?,?,?,?,?,?)",
                ("placeholder",1,1,0,0,"simulated",None,"2026-11-08T00:00:00Z"))
            c.commit();c.close()
            with self.assertRaises(ValueError):
                audit(db=copy)

if __name__=="__main__":unittest.main()
