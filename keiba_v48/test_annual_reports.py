import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from annual_reports import discover, download, connect
from annual_parser import normalize, read_panel
from outline_digits import signature


class AnnualReportsTests(unittest.TestCase):
    def panel_fixture(self, expected=3, note='', jump=False):
        chars = []
        def add(text, x, y, step=3):
            for i, letter in enumerate(text):
                chars.append(dict(text=letter,x0=x+i*step,x1=x+(i+1)*step,
                                  top=y,bottom=y+7,doctop=y,upright=True,height=7,width=step))
        label = '第競走' if jump else '第1競走'
        add('3200111月4日 晴 良 (2023年3福島) 第1日 '+label+' 2歳未勝利 1,700(cid:2)',20,60)
        if jump:
            add('1 テストジャンプ',200,40)
        add('発走9時50分 (ダート・右)',20,75)
        add('負担重量は馬齢重量',20,85)
        for i, (name, odds) in enumerate([('テストイチ','2.0'),('テストニ','4.0'),('テストサン','8.0')],1):
            top=100+i*11
            add(str(i),21,top);add(str(i),30,top);add(name,49,top)
            add('牡2鹿',112,top);add('55',134,top)
            add('騎手',157,top);add('450',308,top);add('+2',321,top)
            add('1:46.9',335,top);add(odds,390,top)
        add(f'({expected}頭)',60,150)
        add('単勝 (cid:2) 200円',20,165)
        if note:
            add(note,20,180)
        return chars

    def test_real_layout_contract_and_concatenated_index_month(self):
        job=dict(year=2023,venue='fukushima',meeting=3,day=1,url='https://www.jra.go.jp/example.pdf')
        race=read_panel(self.panel_fixture(),job,1,0)
        self.assertEqual(race['race_date'],'2023-11-04')
        self.assertEqual(race['distance_m'],1700)
        self.assertEqual(race['status'],'validated_result',race['issues_json'])
        self.assertEqual([r['finish_position'] for r in race['runners']],[1,2,3])
        self.assertTrue(all(r['horse_id'] is None and r['pre_off_odds'] is None for r in race['runners']))

    def test_count_mismatch_never_promotes_ranks(self):
        job=dict(year=2023,venue='fukushima',meeting=3,day=1,url='https://www.jra.go.jp/example.pdf')
        race=read_panel(self.panel_fixture(expected=4),job,1,0)
        self.assertEqual(race['status'],'requires_review')
        self.assertTrue(all(r['finish_position'] is None for r in race['runners']))

    def test_dead_heat_never_promotes_sequential_ranks(self):
        job=dict(year=2023,venue='fukushima',meeting=3,day=1,url='https://www.jra.go.jp/example.pdf')
        race=read_panel(self.panel_fixture(note='同着'),job,1,0)
        self.assertEqual(race['status'],'requires_review')

    def test_graded_jump_number_above_header(self):
        job=dict(year=2023,venue='fukushima',meeting=3,day=1,url='https://www.jra.go.jp/example.pdf')
        race=read_panel(self.panel_fixture(jump=True),job,1,0)
        self.assertIsNotNone(race)
        self.assertEqual(race['race_number'],1)
        self.assertEqual(race['surface'],'jump')

    def test_discovery_all_venues_and_dedup(self):
        html = '<a href="2025/2025-1tokyo1.pdf">PDF</a>' * 2
        jobs = discover(html, 2025)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]['venue'], 'tokyo')
        self.assertEqual(jobs[0]['meeting'], 1)

    def test_discovery_rejects_external_host(self):
        with self.assertRaises(ValueError):
            discover('<a href="https://example.org/2025-1tokyo1.pdf">x</a>', 2025)

    def test_no_links_fail_closed(self):
        with self.assertRaises(ValueError):
            discover('<html>no data</html>', 2025)

    def test_cached_download_no_network(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / '2025' / '2025-1tokyo1.pdf'
            path.parent.mkdir()
            raw = b'%PDF-synthetic-test-signature-only'
            path.write_bytes(raw)
            job = dict(year=2025, venue='tokyo', meeting=1, day=1,
                       url='https://www.jra.go.jp/datafile/seiseki/report/2025/2025-1tokyo1.pdf')
            with patch('annual_reports.fetch', side_effect=AssertionError('network')):
                item = download(job, root)
            self.assertEqual(item['status'], 'downloaded')
            self.assertEqual(item['sha256'], hashlib.sha256(raw).hexdigest())

    def test_non_pdf_stored_as_error(self):
        with tempfile.TemporaryDirectory() as root:
            job = dict(year=2025, venue='tokyo', meeting=1, day=1,
                       url='https://www.jra.go.jp/datafile/seiseki/report/2025/2025-1tokyo1.pdf')
            with patch('annual_reports.fetch', return_value=b'<html>error</html>'):
                self.assertEqual(download(job, root)['status'], 'download_error')

    def test_schema_preserves_legacy_table(self):
        with tempfile.TemporaryDirectory() as root:
            path = str(Path(root) / 'archive.sqlite')
            db = connect(path)
            db.execute('CREATE TABLE races(id INTEGER)')
            db.execute('INSERT INTO races VALUES(418)')
            db.commit(); db.close()
            other = connect(path)
            self.assertEqual(other.execute('SELECT id FROM races').fetchone()[0], 418)
            other.close()

    def test_cid_numeric_range_only(self):
        self.assertEqual(normalize('(cid:9872)(cid:9881)'), '09')
        self.assertEqual(normalize('(cid:9871)'), '(cid:9871)')

    def test_outline_signature_rotation_and_reverse_invariance(self):
        a = [('m',(0.,0.)),('l',(1.,0.)),('l',(1.,2.)),('l',(0.,2.))]
        b = [('m',(11.,22.)),('l',(11.,20.)),('l',(10.,20.)),('l',(10.,22.))]
        self.assertEqual(signature(a), signature(b))

    def test_unrecognized_panel_never_creates_race(self):
        self.assertIsNone(read_panel([], dict(year=2025,venue='tokyo',meeting=1,day=1), 1, 0))

    def test_outline_race_is_quarantined_without_guessing_ids(self):
        # A source-like geometric panel. No numeric fields are synthesized by parser.
        chars = []
        def add(text, x, y, step=4):
            for i, letter in enumerate(text):
                chars.append(dict(text=letter, x0=x+i*step, x1=x+(i+1)*step,
                                  top=y, bottom=y+7, doctop=y, upright=True, height=7,width=step))
        add('第1競走', 230, 60)
        job = dict(year=2025, venue='tokyo', meeting=1, day=1, url='https://www.jra.go.jp/example.pdf')
        race = read_panel(chars, job, 1, 0, outline_recovered=True)
        self.assertEqual(race['status'], 'requires_review')
        self.assertTrue(json.loads(race['metadata_json'])['outline_recovered'])
        self.assertIsNone(race['expected_runners'])
        self.assertEqual(race['runners'], [])


if __name__ == '__main__':
    unittest.main()
