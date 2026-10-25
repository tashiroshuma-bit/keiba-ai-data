"""Synthetic-only tests: these do not establish actual JRA PDF parsing accuracy."""
import unittest
import fitz
from jra_v45_program_layout_probe import probe_pdf_bytes, _header_time


def sample_pdf():
    doc = fitz.open()
    for page_no in range(3):
        p = doc.new_page(width=840, height=595)
        for col in range(4):
            x = col * 210
            race = page_no * 4 + col + 1
            p.insert_text((x + 10, 25), f'{race}R', fontsize=12)
            p.insert_text((x + 10, 40), '10時05分', fontsize=9, fontname='japan')
            for no in (1, 2):
                y = 125 + no * 80
                p.insert_text((x + 12, y), str(no), fontsize=10)
                p.insert_text((x + 75, y), ['ロブチェン', 'アウダーシア'][no - 1],
                              fontsize=10, fontname='japan')
                p.insert_text((x + 152, y), '55', fontsize=10)
    out = doc.tobytes()
    doc.close()
    return out


class ProgramLayoutProbeTest(unittest.TestCase):
    def test_twelve_races_four_columns(self):
        out = probe_pdf_bytes(sample_pdf())
        self.assertEqual(out['race_count'], 12)
        self.assertEqual([x['race_number_expected'] for x in out['races']], list(range(1, 13)))
        self.assertTrue(all(not x['issues'] for x in out['races']))
        self.assertTrue(all(x['post_time_candidate'] == '10:05' for x in out['races']))
        self.assertTrue(all(len(x['runner_candidates']) == 2 for x in out['races']))
        self.assertFalse(out['production_freeze_allowed'])

    def test_reversed_time_unverified(self):
        self.assertEqual(_header_time('Post 発走 分45時9')[1], 'reversed_glyph_order_unverified')

    def test_no_silent_pdf_acceptance(self):
        with self.assertRaisesRegex(ValueError, 'not_a_pdf'):
            probe_pdf_bytes(b'<html>not a PDF</html>')
        doc = fitz.open()
        doc.new_page(width=595, height=842)
        with self.assertRaisesRegex(ValueError, 'unsupported_page_count_or_encrypted'):
            probe_pdf_bytes(doc.tobytes())
        doc.close()

    def test_no_claim_of_independent_official_verification(self):
        out = probe_pdf_bytes(sample_pdf(), 'https://www.jra.go.jp/keiba/rpdf/pdf/example.pdf',
                              '2026-10-25T09:14:00+09:00')
        self.assertEqual(out['status'], 'CANDIDATES_ONLY_UNVERIFIED')
        self.assertTrue(all(x['verified_for_production'] is False for x in out['races']))
        self.assertFalse(out['result_settlement_allowed'])


if __name__ == '__main__':
    unittest.main()
