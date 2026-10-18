import unittest
from pdf_runner_parser import parse_runner_lines,validate
class TestPDFRunnerParser(unittest.TestCase):
 def test_real_pdf_line(self):
  line='1 ② アルナシーム 牡６ 58 藤岡佑介 1:58.1 11-10- 9 - 6 34.6 452（＋２ ） 8.4④ 橋口慎介（栗東） 112'
  rows,errors=parse_runner_lines(line)
  self.assertFalse(errors)
  self.assertEqual(len(rows),1)
  self.assertEqual(rows[0]['horse_number'],2)
  self.assertEqual(rows[0]['final_win_odds'],8.4)
 def test_missing_odds_rejected(self):
  rows,errors=parse_runner_lines('1 ② アルナシーム 牡６ 58 藤岡佑介 missing odds')
  self.assertFalse(rows);self.assertEqual(len(errors),1)
 def test_duplicates(self):
  row=dict(finish_position=1,horse_number=2)
  self.assertIn('duplicate horse numbers',validate([row,row]))
if __name__=='__main__':unittest.main()
