"""Synthetic guardrails only; real 11,201+1,975 JRA data audited separately."""
import unittest
from scripts.jra_review_evidence_v2 import iso_name, FOREIGN, OFFICIAL_META
class ReviewedEvidenceV2Tests(unittest.TestCase):
    def test_repeated_pdf_glyph_exact_recovery(self):
        self.assertEqual(iso_name("セセセセルルルルババババーーーーググググ"),"セルバーグ")
        self.assertEqual(iso_name("トトトトゥゥゥゥーーーードドドドジジジジボボボボンンンン"),"トゥードジボン")
    def test_no_arbitrary_shortened_name_auto_fix(self):
        self.assertNotEqual(iso_name("ファンタスティックムーン"),"ファンタスティック")
    def test_independent_foreign_jra_profile_known(self):
        self.assertEqual(FOREIGN["official_horse_id"],"jra:2020190004")
        self.assertEqual(FOREIGN["official_body_weight"],440)
        self.assertEqual(FOREIGN["official_rank"],11)
        self.assertIn("www.jra.go.jp",FOREIGN["official_profile_url"])
    def test_missing_race_metadata_grounded(self):
        self.assertEqual(OFFICIAL_META["race_id"],"202301020407")
        self.assertEqual(OFFICIAL_META["race_date"],"2023-08-20")
        self.assertEqual(OFFICIAL_META["distance_m"],2000)
        self.assertEqual(OFFICIAL_META["expected_runners"],16)
if __name__=="__main__":unittest.main()
