"""Synthetic-only v48 tests. They cannot prove real JRA PDF parsing or authenticity."""
import copy
import unittest

from jra_v48_candidate_crosscheck import crosscheck_v47

PDF = "https://www.jra.go.jp/keiba/rpdf/pdf/20261025-04tokyo09.pdf"
ROSTER = "https://www.jra.go.jp/keiba/thisweek/20261025/roster.html"


def fixture():
    races, references = [], []
    for n in range(1, 13):
        runners = [dict(horse_number_candidate=i, horse_name_candidate=name,
                        weight_candidate=55.0, name_candidate_count=1, weight_candidate_count=1)
                   for i, name in [(1, "ロブチェン"), (2, "アウダーシア")]]
        races.append(dict(race_number_expected=n, race_number_header_candidates=[n],
                          declared_head_count_candidate=2, post_time_candidate="10:00",
                          post_time_method="direct_text_candidate", runner_candidates=runners,
                          issues=[], verified_for_production=False))
        references.append(dict(race_number=n, post_time="10:00", runners=[
            dict(number=i, name=name, weight=55.0, status="running")
            for i, name in [(1, "ロブチェン"), (2, "アウダーシア")]]))
    probe = dict(schema="jra-v47-program-row-probe", status="CANDIDATES_ONLY_UNVERIFIED",
                 source_url_claimed=PDF, observed_at_claimed="2026-10-25T08:00:00+09:00",
                 pdf_sha256="a" * 64, race_count=12, races=races,
                 source_authenticity_proven=False, official_horse_ids_confirmed=0,
                 production_freeze_allowed=False, result_settlement_allowed=False)
    roster = dict(pdf_sha256="a" * 64, pdf_url=PDF, race_date="20261025",
                  independent_roster_url=ROSTER, independent_roster_sha256="b" * 64,
                  independent_roster_observed_at="2026-10-25T08:10:00+09:00", races=references)
    return probe, roster


class CandidateCrosscheckTest(unittest.TestCase):
    def test_synthetic_clean_still_never_unlocks(self):
        p, r = fixture()
        out = crosscheck_v47(p, r)
        self.assertTrue(out["candidate_consistency_pass"], out["issues"])
        self.assertEqual(out["matched_runner_rows"], 24)
        for key in ("source_authenticity_proven", "production_freeze_allowed",
                    "result_settlement_allowed", "forward_prediction_fixed"):
            self.assertFalse(out[key])
        self.assertEqual(out["official_horse_ids_confirmed"], 0)

    def test_roster_name_mismatch(self):
        p, r = fixture()
        r["races"][0]["runners"][0]["name"] = "ナマエチガイ"
        self.assertFalse(crosscheck_v47(p, r)["candidate_consistency_pass"])

    def test_roster_weight_mismatch(self):
        p, r = fixture()
        r["races"][2]["runners"][0]["weight"] = 57
        self.assertFalse(crosscheck_v47(p, r)["candidate_consistency_pass"])

    def test_after_post_claim_rejected(self):
        p, r = fixture()
        p["observed_at_claimed"] = "2026-10-25T11:00:00+09:00"
        self.assertIn("v46:race_1_not_preoff_observed", crosscheck_v47(p, r)["issues"])

    def test_duplicate_race_number_rejected(self):
        p, r = fixture()
        p["races"][1]["race_number_expected"] = 1
        self.assertFalse(crosscheck_v47(p, r)["candidate_consistency_pass"])

    def test_runner_count_disagreement(self):
        p, r = fixture()
        p["races"][1]["runner_candidates"].pop()
        self.assertIn("race_2_runner_count_mismatch", crosscheck_v47(p, r)["issues"])

    def test_bad_provenance_and_same_source_sha(self):
        p, r = fixture()
        r["independent_roster_sha256"] = p["pdf_sha256"]
        self.assertFalse(crosscheck_v47(p, r)["candidate_consistency_pass"])
        self.assertIn("independent_roster_sha_equals_pdf_sha", crosscheck_v47(p, r)["issues"])

    def test_unsafe_probe_flags_rejected(self):
        p, r = fixture()
        p["production_freeze_allowed"] = True
        self.assertFalse(crosscheck_v47(p, r)["candidate_consistency_pass"])

    def test_unverified_time_rejected(self):
        p, r = fixture()
        p["races"][0]["post_time_method"] = "reversed_glyph_order_unverified"
        self.assertFalse(crosscheck_v47(p, r)["candidate_consistency_pass"])

    def test_non_finite_weight_rejected(self):
        p, r = fixture()
        p["races"][0]["runner_candidates"][0]["weight_candidate"] = float("nan")
        self.assertFalse(crosscheck_v47(p, r)["candidate_consistency_pass"])

    def test_malformed_v46_input_fails_closed(self):
        p, r = fixture()
        r["races"][0]["runners"] = [None]
        self.assertFalse(crosscheck_v47(p, r)["candidate_consistency_pass"])

    def test_original_objects_not_mutated(self):
        p, r = fixture()
        before = copy.deepcopy((p, r))
        crosscheck_v47(p, r)
        self.assertEqual((p, r), before)


if __name__ == "__main__":
    unittest.main()
