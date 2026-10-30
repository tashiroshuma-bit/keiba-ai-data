import ast
import datetime as dt
import re
from pathlib import Path
import unittest
from bs4 import BeautifulSoup
source = Path(__file__).with_name('forecast_20261031_1101_four_model.py').read_text()
tree = ast.parse(source)
names = {'row_number_and_frame','validate_complete_field','parse_official_html'}
namespace = {'re':re,'dt':dt,'JST':dt.timezone(dt.timedelta(hours=9)), 'BeautifulSoup':BeautifulSoup, 'NOW':dt.datetime(2026,10,31,tzinfo=dt.timezone(dt.timedelta(hours=9)))}
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names],type_ignores=[]), '<parser>', 'exec'),namespace)
class FullRosterTest(unittest.TestCase):
    def fixture(self,n=16):
        rows=[]
        for i in range(1,n+1):
            frame=f'<td rowspan="2">{(i+1)//2}</td>' if i%2 else ''
            rows.append(f'<tr>{frame}<td>{i}</td><td><a href="accessU.html?id={i}">馬{i}</a> (0,1,2,3)<a>調教師</a></td><td>52.7</td><td>牡2 56.0 kg <a>騎手</a></td><td>前走 55.0kg 18頭</td></tr>')
        return '<h1>2026年10月31日 東京 1R</h1><p>発走時刻：9時50分 コース：1,600メートル（ダート・左） 天候：曇 ダート：稍重</p><table><tr><th>枠</th><th>馬番</th><th>馬名</th></tr>'+''.join(rows)+'</table>'
    def test_rowspan_all_sixteen_and_current_weight(self):
        h,w,g,s,o=namespace['parse_official_html'](self.fixture(),'2026-10-31','東京',1)
        self.assertEqual([x['number'] for x in h],list(range(1,17)))
        self.assertTrue(all(x['assigned_weight_kg']==56 for x in h))
        self.assertEqual((w,g,s),('曇','稍重','dirt'))
    def test_mobile_compact_current_weight(self):
        rows=[]
        for i in range(1,17):
            frame=f'<td class="wban" rowspan="2">{(i+1)//2}</td>' if i%2 else ''
            rows.append(f'<tr>{frame}<td class="uban">{i}</td><td class="uma"><a href="accessU.html?id={i}">馬{i}</a> 52.7 (16番人気) 牡2 / 青鹿 (0,1,2,3) <a>騎手</a> (56.0) <a>調教師</a></td></tr>')
        html='<h1>2026年10月31日 東京 1R</h1><p>発走時刻：9時50分 コース：1,600メートル（ダート・左）</p><table><tr><th>馬番</th><th>馬名</th></tr>'+''.join(rows)+'</table>'
        h,*_=namespace['parse_official_html'](html,'2026-10-31','東京',1)
        self.assertEqual(len(h),16)
        self.assertTrue(all(x['assigned_weight_kg']==56 for x in h))
    def test_reject_old_odd_only_subset(self):
        with self.assertRaisesRegex(ValueError,'FIELD_NUMBER_GAPS'):
            namespace['validate_complete_field']([{'number':n,'name':f'馬{n}'} for n in range(1,17,2)])
    def test_missing_last_runner_requires_independent_check(self):
        # Contiguity alone cannot detect trailing loss; production additionally matches Yahoo's full roster.
        h,*_=namespace['parse_official_html'](self.fixture(15),'2026-10-31','東京',1)
        self.assertNotEqual({x['number'] for x in h},set(range(1,17)))
    def test_reject_no_records(self):
        with self.assertRaisesRegex(ValueError,'CAREER_RECORD_MISSING'):
            namespace['parse_official_html'](self.fixture().replace('(0,1,2,3)',''),'2026-10-31','東京',1)
    def test_reject_weight_from_odds(self):
        with self.assertRaisesRegex(ValueError,'ASSIGNED_WEIGHT_CELL_MISSING'):
            namespace['parse_official_html'](self.fixture().replace('56.0 kg',''),'2026-10-31','東京',1)
if __name__=='__main__': unittest.main()
