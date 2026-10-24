import unittest
from datetime import datetime, timedelta, timezone
from scripts.external_muryou_keiba_reference import snapshot, compare, parse_prediction, validate_url

JST = timezone(timedelta(hours=9))
HTML = """<html><body>競馬予想の更新日：2026年10月24日 17時10分
<table><tr><th>馬番</th><th>馬名・騎手名</th><th>人気</th><th>AI予想</th></tr>
<tr><td>8</td><td>ロブチェン 松山</td><td>1 1.7倍</td><td>◎78.4</td></tr>
<tr><td>9</td><td>ゴーイントゥスカイ 武</td><td>3 12.6倍</td><td>○69.2</td></tr>
<tr><td>3</td><td>アウダーシア 津村</td><td>5 21.9倍</td><td>▲68.0</td></tr></table></body></html>"""
URL = "https://muryou-keiba-ai.jp/predict/2026/10/22/25187/"
class ExternalReferenceTests(unittest.TestCase):
    def test_extract_and_compare(self):
        data = snapshot(URL, datetime(2026,10,24,21,30,tzinfo=JST), datetime(2026,10,25,15,40,tzinfo=JST), HTML)
        self.assertEqual([x["horse_number"] for x in data["horses"]], [8,9,3])
        self.assertEqual([x["index"] for x in data["horses"]], [78.4,69.2,68.0])
        result = compare(data,[{"number":8},{"number":3},{"number":9}])
        self.assertEqual(result["status"],"COMPARED_INDEPENDENTLY")
        self.assertEqual(result["external_top3"],[8,9,3])
        self.assertEqual(result["internal_top3"],[8,3,9])
    def test_reject_unsafe_host(self):
        for u in ["https://muryou-keiba-ai.jp.evil.test/predict/a", "http://muryou-keiba-ai.jp/predict/a","https://evil.test/predict/a"]:
            with self.assertRaises(ValueError):
                validate_url(u)
    def test_reject_post_off(self):
        with self.assertRaises(ValueError):
            snapshot(URL,datetime(2026,10,25,15,37,tzinfo=JST),datetime(2026,10,25,15,40,tzinfo=JST),HTML)
    def test_reject_future_update(self):
        with self.assertRaises(ValueError):
            snapshot(URL,datetime(2026,10,24,16,0,tzinfo=JST),datetime(2026,10,25,15,40,tzinfo=JST),HTML)
    def test_roster_mismatch(self):
        data = snapshot(URL,datetime(2026,10,24,21,30,tzinfo=JST),datetime(2026,10,25,15,40,tzinfo=JST),HTML)
        self.assertEqual(compare(data,[{"number":8}])["status"],"ROSTER_MISMATCH")

if __name__ == "__main__":
    unittest.main()
