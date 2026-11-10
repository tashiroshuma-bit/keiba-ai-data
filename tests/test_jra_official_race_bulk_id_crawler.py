import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts.jra_official_race_bulk_id_crawler import (
    parse_html,race_id_from_url,approved_result_url,run)
URL="https://www.jra.go.jp/JRADB/accessS.html?CNAME=pw01sde1001202301010120230722%2F4A"
NEXT="https://www.jra.go.jp/JRADB/accessS.html?CNAME=pw01sde1001202301010220230722/7E"
def page():
    def tr(i):
        return f'<tr><td>{i}</td><td>枠</td><td class="num">{i}</td><td class="horse"><a href="/JRADB/accessU.html?CNAME=pw01dud10202110000{i}/AB">テスト{i}</a></td></tr>'
    return ('<html><body><table><tbody>'+''.join(tr(i) for i in (1,2,3))+
        f'</tbody></table><a href="{NEXT}">next</a></body></html>').encode()
class Response:
    status=200
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self,n):return page()
class JraBulkCrawlerTests(unittest.TestCase):
    def test_real_race_url_decoder_and_host_validation(self):
        self.assertEqual(race_id_from_url(URL),"202301010101")
        self.assertEqual(race_id_from_url("https://www.jra.go.jp/JRADB/accessS.html?CNAME=pw01sde0108202604070120261018%2F9A"),"202608040701")
        self.assertTrue(approved_result_url(URL))
        self.assertFalse(approved_result_url(URL.replace("www.jra.go.jp","bad.example")))
    def test_official_rows_and_race_neighbors(self):
        rows,neighbors=parse_html(page(),URL)
        self.assertEqual(len(rows),3)
        self.assertEqual(rows[0]["horse_number"],1)
        self.assertEqual(rows[0]["horse_id"],"jra:2021100001")
        self.assertEqual(neighbors,[NEXT])
    def test_archives_raw_bytes_and_prevents_overwrite(self):
        with tempfile.TemporaryDirectory() as d, patch("urllib.request.urlopen",return_value=Response()):
            report=run([URL],Path(d)/"out",max_pages=1,delay=1)
            self.assertEqual(report["horse_rows"],3)
            saved=Path(d)/"out"/"official_race_horse_ids.json"
            data=json.loads(saved.read_bytes())
            self.assertEqual(data["records"][0]["race_id"],"202301010101")
            source_sha=hashlib.sha256(page()).hexdigest()
            self.assertEqual((Path(d)/"out"/"raw"/(source_sha+".bin")).read_bytes(),page())
            with self.assertRaises(FileExistsError):
                run([URL],Path(d)/"out",max_pages=1,delay=1)
if __name__=="__main__":unittest.main()
