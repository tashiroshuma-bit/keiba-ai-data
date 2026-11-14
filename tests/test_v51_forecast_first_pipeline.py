import json
import tempfile
import unittest
from pathlib import Path

from scripts.v51_forecast_first_pipeline import run


class ForecastFirstPipelineTests(unittest.TestCase):
    def test_missing_input_fails_closed_and_writes_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            out = root / "out"
            with self.assertRaises(FileNotFoundError):
                run(root / "missing_snapshot.json", root / "missing.sqlite", out)
            manifest = json.loads((out / "run_manifest.json").read_text())
            self.assertEqual(manifest["status"], "FAILED")
            self.assertIn("VERIFIED_PREOFF_SNAPSHOT_MISSING", manifest["error"])
            self.assertFalse((out / "forecast.json").exists())

    def test_missing_db_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            snap = root / "snapshot.json"
            snap.write_text("{}")
            with self.assertRaises(FileNotFoundError):
                run(snap, root / "missing.sqlite", root / "out")
            manifest = json.loads((root / "out" / "run_manifest.json").read_text())
            self.assertIn("CANONICAL_DATABASE_MISSING", manifest["error"])


if __name__ == "__main__":
    unittest.main()
