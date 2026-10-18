import unittest, tempfile
from pathlib import Path
from bulk_ingest import run
class Tests(unittest.TestCase):
 def test_no_network_when_offline_indexes_missing(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); (root/"indexes").mkdir()
   result=run(str(root/"x.db"),str(root/"pdf"),index_dir=str(root/"indexes"))
   self.assertEqual(result["races_indexed"],0)
   self.assertEqual(len(result["index_errors"]),3)
 def test_index_resume(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); idx=root/"indexes";idx.mkdir()
   (idx/"2025.html").write_text("""<table><tr><th>月日</th><th>レース名</th><th>競馬場</th><th>性齢</th><th>コース</th><th>優勝馬</th><th>騎手</th><th>結果</th><th>プレイバック</th></tr>
<tr><td>1月5日日曜</td><td>GⅢ中山金杯</td><td>中山</td><td>4歳以上</td><td>芝2,000メートル</td><td>アルナシーム</td><td>藤岡</td><td></td><td></td></tr></table>""")
   a=run(str(root/"x.db"),str(root/"pdf"),years=(2025,),index_dir=str(idx))
   self.assertEqual(a["races_indexed"],1)
   self.assertEqual(a["new_pdf_jobs"],0)
if __name__=="__main__":unittest.main()
