import unittest, sqlite3
from jra_pdf_archive import parse_index,dbconnect
HTML="""<table><tr><th>月日</th><th>レース名</th><th>競馬場</th><th>性齢</th><th>コース</th><th>優勝馬</th><th>騎手</th><th>結果</th><th>プレイバック</th></tr>
<tr><td>1月5日日曜</td><td>GⅢ中山金杯</td><td>中山</td><td>4歳以上</td><td>芝2,000メートル</td><td>アルナシーム</td><td>藤岡</td><td><a href="result.html">レース結果</a></td><td><a href="pdf/001.pdf">playback</a></td></tr></table>"""
class TestArchive(unittest.TestCase):
 def test_index(self):
  rows=parse_index(HTML,2025)
  self.assertEqual(len(rows),1)
  self.assertEqual(rows[0]["race_date"],"2025-01-05")
  self.assertTrue(rows[0]["pdf_url"].endswith("/2025/pdf/001.pdf"))
 def test_empty_index(self):
  with self.assertRaises(ValueError):parse_index("<html/>",2024)
 def test_schema(self):
  c=dbconnect(":memory:")
  self.assertEqual(c.execute("select count(*) from runner_results").fetchone()[0],0)
if __name__=="__main__":unittest.main()
