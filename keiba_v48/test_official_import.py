import unittest
from official_import import parse
class Tests(unittest.TestCase):
 def test_result(self):
  headers=['着順','枠','馬番','馬名','性齢','負担重量','騎手','タイム','着差','コーナー','上り','馬体重','調教師','単勝人気']
  vals=['1','5','11','架空馬','牝3','55.0','架空騎手','1:59.1','','1 1 1','34.0','450(+2)','架空厩舎','2']
  html='<table><tr>'+''.join('<th>'+v+'</th>' for v in headers)+'</tr><tr>'+''.join('<td>'+v+'</td>' for v in vals)+'</tr></table>'
  r=parse(html);self.assertEqual(r[0]['horse_number'],'11');self.assertEqual(r[0]['body_weight'],'450')
 def test_no_table(self):
  with self.assertRaises(ValueError):parse('<html></html>')
if __name__=='__main__':unittest.main()
