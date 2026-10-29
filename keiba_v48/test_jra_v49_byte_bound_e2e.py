"""v49 offline byte-binding tests; synthetic PDFs, NOT real JRA validation."""
import copy
import hashlib
import unittest
from unittest.mock import patch

import fitz
from jra_v49_byte_bound_e2e import inspect_bytes

URL = "https://www.jra.go.jp/keiba/rpdf/pdf/20261025-04tokyo09.pdf"
OTHER = "https://www.jra.go.jp/keiba/thisweek/20261025/roster.html"


def fixture():
    doc = fitz.open()
    for _ in range(3):
        doc.new_page(width=1200, height=700)
    program = doc.tobytes()
    doc.close()
    raw = b"<html><body>independent source fixture</body></html>"
    roster = {"pdf_sha256": hashlib.sha256(program).hexdigest(),
              "independent_roster_sha256": hashlib.sha256(raw).hexdigest(),
              "pdf_url": URL, "independent_roster_url": OTHER,
              "race_date": "20261025", "independent_roster_observed_at": "2026-10-25T08:10:00+09:00",
              "races": []}
    return program, raw, roster


class ByteBoundTest(unittest.TestCase):
    def test_real_synthetic_pdf_integration_rejects_missing_runners(self):
        p, raw, roster = fixture()
        result = inspect_bytes(p, raw, roster, URL, "2026-10-25T08:00:00+09:00")
        self.assertTrue(result["byte_hashes_bound"])
        self.assertFalse(result["candidate_consistency_pass"])
        self.assertEqual(result["program_pdf_sha256_computed"], roster["pdf_sha256"])
        self.assertFalse(result["production_freeze_allowed"])

    def test_pdf_hash_tampering_rejected(self):
        p, raw, roster = fixture()
        roster["pdf_sha256"] = "a" * 64
        self.assertIn("roster_program_sha_not_bound_to_bytes", inspect_bytes(p, raw, roster, URL, "2026-10-25T08:00:00+09:00")["issues"])

    def test_independent_hash_tampering_rejected(self):
        p, raw, roster = fixture()
        roster["independent_roster_sha256"] = "b" * 64
        self.assertIn("roster_independent_sha_not_bound_to_bytes", inspect_bytes(p, raw, roster, URL, "2026-10-25T08:00:00+09:00")["issues"])

    def test_identical_bytes_rejected(self):
        p, raw, roster = fixture()
        roster["independent_roster_sha256"] = hashlib.sha256(p).hexdigest()
        self.assertIn("independent_bytes_identical_to_program", inspect_bytes(p, p, roster, URL, "2026-10-25T08:00:00+09:00")["issues"])

    def test_url_disagreement_rejected(self):
        p, raw, roster = fixture()
        roster["pdf_url"] = "https://other.example/pdf"
        self.assertIn("roster_program_url_disagrees", inspect_bytes(p, raw, roster, URL, "2026-10-25T08:00:00+09:00")["issues"])

    def test_non_pdf_rejected(self):
        _, raw, roster = fixture()
        with self.assertRaisesRegex(ValueError, "program_not_pdf"):
            inspect_bytes(b"fake", raw, roster, URL, "2026-10-25T08:00:00+09:00")

    def test_empty_independent_rejected(self):
        p, _, roster = fixture()
        with self.assertRaisesRegex(ValueError, "independent_source_empty"):
            inspect_bytes(p, b"", roster, URL, "2026-10-25T08:00:00+09:00")

    def test_inputs_not_mutated(self):
        p, raw, roster = fixture()
        before = copy.deepcopy(roster)
        inspect_bytes(p, raw, roster, URL, "2026-10-25T08:00:00+09:00")
        self.assertEqual(before, roster)

    def test_even_mock_clean_match_never_authorizes_production(self):
        p, raw, roster = fixture()
        with patch("jra_v49_byte_bound_e2e.probe_pdf_bytes", return_value={"schema": "mock"}), \
             patch("jra_v49_byte_bound_e2e.crosscheck_v47", return_value={"candidate_consistency_pass": True, "matched_runner_rows": 180, "issues": []}):
            result = inspect_bytes(p, raw, roster, URL, "2026-10-25T08:00:00+09:00")
        self.assertTrue(result["candidate_consistency_pass"])
        self.assertEqual(result["matched_runner_rows"], 180)
        for key in ("source_authenticity_proven", "capture_time_authenticated",
                    "scratches_authenticated", "production_freeze_allowed", "result_settlement_allowed",
                    "forward_prediction_fixed"):
            self.assertFalse(result[key])

    def test_malformed_parser_fails_closed(self):
        p, raw, roster = fixture()
        with patch("jra_v49_byte_bound_e2e.probe_pdf_bytes", side_effect=ValueError("bad_pdf")):
            result = inspect_bytes(p, raw, roster, URL, "2026-10-25T08:00:00+09:00")
        self.assertFalse(result["candidate_consistency_pass"])
        self.assertIn("probe_or_crosscheck_failed:ValueError", result["issues"])


if __name__ == "__main__":
    unittest.main()
