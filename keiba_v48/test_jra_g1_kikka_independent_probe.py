"""Synthetic fixtures only; actual JRA source validation runs in isolated CI."""
import unittest
from unittest.mock import patch
from jra_g1_kikka_independent_probe import parse_g1_html, compare_kyoto11

def html(rows=18, duplicate=False, weight="57.0 kg", header="菊花賞"):
    trs = []
    for n in range(1, rows + 1):
        k = 1 if duplicate and n == 18 else n
        trs.append(f"<tr><td>{(n + 1) // 2}</td><td>{k}</td>"
                   f"<td><a>テストホース{n}</a></td><td>牡3 {weight} 武豊</td>"
                   "<td>過去 55.0 kg</td></tr>")
    # Fixtures use kana-only names as production validation requires.
    trs = [r.replace(f"テストホース{n}", "テストホース" + chr(0x30A0 + n))
           for n, r in enumerate(trs, 1)]
    return (f"<html><body><h1>{header}</h1><p>2026年10月25日 発走時刻：15時40分</p>"
            "<table><tr><th>枠</th><th>馬番</th><th>馬名</th><th>負担重量</th></tr>"
            + "".join(trs) + "</table></body></html>").encode()

class G1IndependentTest(unittest.TestCase):
    def test_complete_table(self):
        r = parse_g1_html(html())
        self.assertEqual(r["runner_count"], 18)
        self.assertEqual([x["number"] for x in r["runners"]], list(range(1, 19)))
        self.assertTrue(all(x["weight"] == 57 for x in r["runners"]))
    def test_incomplete_rejected(self):
        with self.assertRaisesRegex(ValueError, "unique_complete"):
            parse_g1_html(html(rows=17))
    def test_duplicate_number_rejected(self):
        with self.assertRaisesRegex(ValueError, "unique_complete"):
            parse_g1_html(html(duplicate=True))
    def test_wrong_race_rejected(self):
        with self.assertRaisesRegex(ValueError, "wrong_race"):
            parse_g1_html(html(header="天皇賞"))
    def test_history_weight_not_used(self):
        with self.assertRaisesRegex(ValueError, "unique_complete"):
            parse_g1_html(html(weight="不明"))
    def test_crossdocument_never_unfreezes(self):
        probe = {"pdf_sha256": "a"*64, "races": [{} for _ in range(12)]}
        probe["races"][10] = {
            "race_number_header_candidates": [11], "post_time_candidate": "15:40",
            "post_time_method": "direct_text_candidate",
            "runner_candidates": [{"horse_number_candidate": x["number"],
                                   "horse_name_candidate": x["name"],
                                   "weight_candidate": x["weight"]}
                                  for x in parse_g1_html(html())["runners"]],
            "declared_head_count_candidate": None,
            "issues": ["declared_head_count_missing_or_ambiguous"]}
        with patch("jra_g1_kikka_independent_probe.probe_pdf_bytes", return_value=probe):
            r = compare_kyoto11(b"%PDF-fake", html(),
                                pdf_observed_at="2026-10-31T01:00:00Z",
                                html_observed_at="2026-10-31T01:00:01Z")
        self.assertEqual(r["matched_number_name_weight"], 18)
        self.assertTrue(r["full_crossdocument_match"])
        self.assertIn("pdf_printed_headcount_not_machine_decoded", r["issues"])
        self.assertFalse(r["production_freeze_allowed"])
        self.assertFalse(r["preoff_capture_proven"])

if __name__ == "__main__":
    unittest.main()
