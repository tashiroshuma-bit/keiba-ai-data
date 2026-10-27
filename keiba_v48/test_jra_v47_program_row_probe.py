"""Only synthetic geometry tests. Never cite as real JRA PDF extraction proof."""
import unittest
import fitz
from jra_v47_program_row_probe import probe_pdf_bytes


def fixture(*, weight_x=.55, missing_weight=False, duplicate=False, reversed_time=False,
            second_name=False, missing_runner=False):
    doc = fitz.open()
    for page_no in range(3):
        p = doc.new_page(width=1200, height=750)
        for col in range(4):
            x = col * 300
            race = page_no * 4 + col + 1
            p.insert_text((x + 10, 28), f"{race}R", fontsize=15)
            p.insert_text((x + 110, 40), "頭2", fontsize=9, fontname="japan")
            p.insert_text((x + 15, 68), "分50時9" if reversed_time else "9時50分", fontsize=11, fontname="japan")
            for no in ((1,) if missing_runner else (1, 2)):
                y = 170 + no * 90
                p.insert_text((x + 28, y), str(no), fontsize=13)
                p.insert_text((x + 90, y), "ロブチェン" if no == 1 else "アウダーシア", fontsize=12, fontname="japan")
                if second_name and no == 1:
                    p.insert_text((x + 118, y), "別名", fontsize=11, fontname="japan")
                if not missing_weight:
                    p.insert_text((x + weight_x * 300, y), "55", fontsize=11)
                p.insert_text((x + 225, y), "ヨコヤマ", fontsize=9, fontname="japan")
                p.insert_text((x + 90, y + 17), "キタサンブラック", fontsize=6, fontname="japan")
                p.insert_text((x + 165, y + 17), "56", fontsize=7)
            if duplicate:
                p.insert_text((x + 28, 450), "1", fontsize=13)
    result = doc.tobytes()
    doc.close()
    return result


class ProgramRowProbeTest(unittest.TestCase):
    def test_official_like_weight_column_and_multiline_pedigree(self):
        out = probe_pdf_bytes(fixture())
        self.assertEqual(out["race_count"], 12)
        for race in out["races"]:
            self.assertEqual(race["post_time_candidate"], "09:50")
            self.assertEqual(race["issues"], [])
            self.assertEqual([r["horse_name_candidate"] for r in race["runner_candidates"]], ["ロブチェン", "アウダーシア"])
            self.assertEqual([r["weight_candidate"] for r in race["runner_candidates"]], [55.0, 55.0])
        self.assertFalse(out["production_freeze_allowed"])
        self.assertFalse(out["source_authenticity_proven"])

    def test_legacy_wrong_weight_band_fails_closed(self):
        out = probe_pdf_bytes(fixture(weight_x=.75))
        self.assertTrue(all("name_or_weight_ambiguous" in x["issues"] for x in out["races"]))

    def test_missing_weight_fails_closed(self):
        out = probe_pdf_bytes(fixture(missing_weight=True))
        self.assertTrue(all("name_or_weight_ambiguous" in x["issues"] for x in out["races"]))

    def test_ambiguous_name_fails_closed(self):
        out = probe_pdf_bytes(fixture(second_name=True))
        self.assertTrue(all("name_or_weight_ambiguous" in x["issues"] for x in out["races"]))

    def test_duplicate_number_fails_closed(self):
        out = probe_pdf_bytes(fixture(duplicate=True))
        self.assertTrue(all("duplicate_runner_anchor" in x["issues"] for x in out["races"]))

    def test_missing_number_fails_closed(self):
        out = probe_pdf_bytes(fixture(missing_runner=True))
        self.assertEqual(len(out["races"][0]["runner_candidates"]), 1)
        self.assertIn("runner_count_disagrees_with_header", out["races"][0]["issues"])
        self.assertFalse(out["production_freeze_allowed"])

    def test_reversed_time_not_verified(self):
        out = probe_pdf_bytes(fixture(reversed_time=True))
        self.assertTrue(all(x["post_time_method"] == "reversed_glyph_order_unverified" for x in out["races"]))
        self.assertTrue(all("post_time_not_directly_readable" in x["issues"] for x in out["races"]))

    def test_invalid_pdf_and_wrong_geometry(self):
        with self.assertRaisesRegex(ValueError, "not_a_pdf"):
            probe_pdf_bytes(b"<html/>")
        doc = fitz.open()
        doc.new_page(width=595, height=842)
        with self.assertRaisesRegex(ValueError, "unsupported_pdf_geometry_or_encrypted"):
            probe_pdf_bytes(doc.tobytes())
        doc.close()

    def test_claimed_time_and_url_are_not_authenticity(self):
        out = probe_pdf_bytes(fixture(), "https://www.jra.go.jp/keiba/rpdf/pdf/20261025-04tokyo09.pdf", "2026-10-25T08:00:00+09:00")
        self.assertFalse(out["source_authenticity_proven"])
        self.assertEqual(out["official_horse_ids_confirmed"], 0)
        self.assertFalse(out["result_settlement_allowed"])


if __name__ == "__main__":
    unittest.main()
