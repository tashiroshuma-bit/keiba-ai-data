import json
import tempfile
import unittest
from pathlib import Path

from scripts.v51_preoff_diagnostics import check


class TestV51PreoffDiagnostics(unittest.TestCase):
    def test_missing_inputs_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            policy = root / "policy.json"
            policy.write_text(json.dumps({
                "expected_canonical_db_sha256": "a" * 64,
                "requires_feature_schema": "jra-v51-preoff-feature-snapshot-v1"
            }))
            result = check(root / "missing.json", root / "missing.sqlite",
                           root / "missing-model.json", policy)
            self.assertEqual(result["status"], "NOT_READY")
            self.assertIn("database:MISSING", result["issues"])
            self.assertIn("model:MISSING", result["issues"])
            self.assertIn("snapshot:MISSING", result["issues"])

    def test_nonfinite_feature_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            policy = root / "policy.json"
            policy.write_text(json.dumps({
                "expected_canonical_db_sha256": "a" * 64,
                "requires_feature_schema": "jra-v51-preoff-feature-snapshot-v1"
            }))
            snap = root / "snap.json"
            snap.write_text(json.dumps({
                "schema": "jra-v51-preoff-feature-snapshot-v1",
                "canonical_database_sha256": "a" * 64,
                "forecast_asof": "2026-11-15T08:00:00+09:00",
                "roster_source_url": "https://www.jra.go.jp/",
                "roster_source_sha256": "b" * 64,
                "races": [{
                    "race": "KYOTO11",
                    "race_off_at": "2026-11-15T15:00:00+09:00",
                    "horses": [
                        {"number": i, "horse_id": "jra:test" + str(i),
                         "official_identity_proof": {},
                         "feature_values": [float("nan")] + [0] * 30,
                         "features_observed_at": "2026-11-15T07:00:00+09:00"}
                        for i in range(1, 4)
                    ]
                }]
            }))
            result = check(snap, root / "missing.sqlite", root / "missing-model.json", policy)
            self.assertIn("KYOTO11/1:INVALID_FEATURES", result["issues"])

    def test_unproven_horse_and_late_feature_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            policy = root / "policy.json"
            policy.write_text(json.dumps({
                "expected_canonical_db_sha256": "a" * 64,
                "requires_feature_schema": "jra-v51-preoff-feature-snapshot-v1"
            }))
            snap = root / "snap.json"
            snap.write_text(json.dumps({
                "schema": "jra-v51-preoff-feature-snapshot-v1",
                "canonical_database_sha256": "a" * 64,
                "forecast_asof": "2026-11-15T08:00:00+09:00",
                "roster_source_url": "https://www.jra.go.jp/",
                "roster_source_sha256": "b" * 64,
                "races": [{
                    "race": "KYOTO11", "race_off_at": "2026-11-15T15:00:00+09:00",
                    "horses": [
                        {"number": i, "horse_id": "unknown", "feature_values": [0] * 31,
                         "features_observed_at": "2026-11-15T16:00:00+09:00"}
                        for i in range(1, 4)
                    ]
                }]
            }))
            result = check(snap, root / "missing.sqlite", root / "missing-model.json", policy)
            self.assertIn("KYOTO11/1:MISSING_ID_PROOF", result["issues"])
            self.assertIn("KYOTO11/1:FEATURE_AFTER_ASOF", result["issues"])
            self.assertEqual(result["status"], "NOT_READY")


if __name__ == "__main__":
    unittest.main()
