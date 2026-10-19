import datetime as dt
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

from bs4 import BeautifulSoup
from annual_reports import connect
from official_linkage import SourceCache, attest, links, normalized, parse_result, propagate, race_key, schema
from historical_replay import assumed_availability, load_rows, select_index
from features import HistoryIndex
from fitted_model import HierarchicalModel

URL = 'https://www.jra.go.jp/JRADB/accessS.html?CNAME=pw01sde1004202501050920250517/0B'


def fixture(date='2025年5月17日', age=5):
    return BeautifulSoup(f'''<table class="basic narrow-xy"><caption>
      <div class="date_line"><div class="date">{date}（土曜）1回新潟5日</div><div class="time">発走時刻：14時16分</div></div>
      <div class="race_number"><img alt="9レース"></div></caption><tbody><tr>
      <td class="place">1</td><td class="num">5</td><td class="horse">
      <a href="/JRADB/accessU.html?CNAME=pw01dud102020100678/D3">アンテロース</a></td>
      <td class="age">牡{age}</td><td class="jockey"><a onclick="return doAction('/JRADB/accessK.html', 'pw04kmk001095/AD');">吉田 隼人</a></td>
      </tr></tbody></table>''', 'html.parser')


class OfficialLinkageTests(unittest.TestCase):
    def db_fixture(self, folder):
        path = str(Path(folder) / 'test.sqlite')
        db = connect(path); schema(db)
        db.execute("INSERT INTO annual_report_documents(url,year,venue,meeting,day,status,fetched_at) VALUES('https://www.jra.go.jp/source.pdf',2025,'niigata',1,5,'parsed','2026-10-19T00:00:00+00:00')")
        for num in (5, 6, 7):
            payload = dict(sex_age='牡5',horse_name='アンテロース',jockey_name='吉田隼人',
                           identity_status='names_only_unlinked',finish_position=num-4,final_win_odds=2.0)
            db.execute('''INSERT OR IGNORE INTO annual_report_races VALUES
              ('202504010509','https://www.jra.go.jp/source.pdf',1,0,9,'2025-05-17','新潟','turf',2000,'良',
               '2025-05-17T14:15:00+09:00',3,'validated_result','[]','{"win_payout_100":200}')''')
            db.execute("INSERT INTO annual_report_runners VALUES('202504010509',?,?, 'アンテロース','吉田隼人',NULL,NULL,?)",
                       (num,num-4,json.dumps(payload,ensure_ascii=False)))
        db.commit()
        return path, db

    def test_parses_actual_style_source_ids_and_validates_date_age(self):
        self.assertEqual(race_key(URL), ('202504010509', '2025-05-17'))
        row = parse_result(fixture(), URL)[0]
        self.assertEqual(row['horse_id'], 'jra:2020100678')
        self.assertEqual(row['jockey_id'], 'jra:001095')
        self.assertEqual(row['source_finish_position'], 1)
        with self.assertRaises(ValueError): parse_result(fixture(age=4), URL)
        with self.assertRaises(ValueError): parse_result(fixture(date='2025年5月18日'), URL)

    def test_source_links_are_discovered_not_checksum_guessed(self):
        soup = BeautifulSoup('''<a href="/JRADB/accessS.html?CNAME=pw01sde1004202501050920250517/0B">x</a>
          <a onclick="doAction('/JRADB/accessK.html','pw04kmk001095/AD')">j</a>''', 'html.parser')
        self.assertEqual(len(links(soup, URL)), 2)

    def test_rejects_external_source_and_stops_at_permission_error(self):
        with tempfile.TemporaryDirectory() as root:
            cache = SourceCache(root)
            with self.assertRaises(ValueError): cache.get('https://example.org/file')
            session = Mock(); session.get.return_value.status_code = 403
            with patch('official_linkage._LOCAL', Mock(session=session)):
                with self.assertRaises(PermissionError): cache.get(URL)
            self.assertFalse(list(Path(root).glob('*.html')))

    def test_attestation_requires_race_number_name_age_and_detects_conflict(self):
        with tempfile.TemporaryDirectory() as root:
            _, db = self.db_fixture(root)
            meta = dict(url=URL, sha256='a'*64, observed_at='2026-10-19T00:00:00+00:00')
            row = parse_result(fixture(), URL)[0]
            self.assertEqual(attest(db,[{**row,'horse_name':'別の馬'}],meta),0)
            self.assertEqual(attest(db,[{**row,'birth_year':2019}],meta),0)
            self.assertEqual(attest(db,[row],meta),1)
            with self.assertRaises(ValueError): attest(db,[{**row,'horse_id':'jra:2020100999'}],meta)
            db.close()

    def test_conflicting_name_birth_key_is_not_propagated(self):
        with tempfile.TemporaryDirectory() as root:
            _, db = self.db_fixture(root)
            meta = dict(url=URL, sha256='a'*64, observed_at='2026-10-19T00:00:00+00:00')
            row = parse_result(fixture(), URL)[0]
            attest(db,[row],meta)
            attest(db,[{**row,'horse_number':6,'horse_id':'jra:2020100999'}],meta)
            report = propagate(db)
            self.assertEqual(report['ambiguous_horse_keys'],1)
            self.assertEqual(report['horse_linked_rows'],2)  # exact attested rows remain valid
            self.assertIsNone(db.execute("SELECT horse_id FROM annual_report_runners WHERE horse_number=7").fetchone()[0])
            self.assertEqual(report['jockey_linked_rows'],3)
            self.assertEqual(db.execute('SELECT count(*) FROM annual_time_evidence WHERE result_published_at IS NOT NULL').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT scheduled_off_at,result_page_off_at,actual_off_at FROM annual_time_evidence').fetchone(),
                ('2025-05-17T14:15:00+09:00','2025-05-17T14:16:00+09:00',None))
            db.close()

    def test_research_time_is_explicit_assumption_and_ties_ignore_labels(self):
        self.assertEqual(assumed_availability('2023-12-31',2),'2024-01-02T00:00:00+09:00')
        with self.assertRaises(ValueError): assumed_availability('2025-01-01',1)
        rows=[{'horse_number':'9','finish_position':1},{'horse_number':'2','finish_position':3},
              {'horse_number':'4','finish_position':2}]
        self.assertEqual(select_index([1/3]*3,rows),1)
        with self.assertRaisesRegex(ValueError, 'research-only'):
            HistoryIndex([{'availability_basis':'assumed_calendar_day_lag_for_research_only'}])
        with self.assertRaisesRegex(ValueError, 'research-only'):
            HierarchicalModel.from_dict({'research_only':True})

    def test_replay_excludes_duplicate_official_identity_and_postrace_current_fields(self):
        with tempfile.TemporaryDirectory() as root:
            path, db = self.db_fixture(root)
            meta = dict(url=URL, sha256='a'*64, observed_at='2026-10-19T00:00:00+00:00')
            attest(db,parse_result(fixture(),URL),meta); propagate(db); db.commit(); db.close()
            history, rows, excluded = load_rows(path)
            self.assertEqual(len(history),3)
            self.assertEqual(rows,[])
            self.assertEqual(excluded['duplicate_identity_races'],1)

    def test_reparse_cannot_reuse_stale_runner_identity(self):
        with tempfile.TemporaryDirectory() as root:
            _, db = self.db_fixture(root)
            meta = dict(url=URL,sha256='a'*64,observed_at='2026-10-19T00:00:00+00:00')
            attest(db,parse_result(fixture(),URL),meta)
            db.execute("UPDATE annual_report_runners SET horse_name='別の馬' WHERE horse_number=5")
            propagate(db)
            self.assertIsNone(db.execute('SELECT horse_id FROM annual_report_runners WHERE horse_number=5').fetchone()[0])
            db.close()

    def test_refresh_preserves_existing_observed_times(self):
        with tempfile.TemporaryDirectory() as root:
            _, db = self.db_fixture(root)
            propagate(db)
            db.execute("UPDATE annual_time_evidence SET actual_off_at='2025-05-17T14:16:01+09:00',result_published_at='2025-05-18T12:00:00+09:00',result_first_observed_at='2025-05-18T12:01:00+09:00'")
            propagate(db)
            self.assertEqual(db.execute('SELECT actual_off_at,result_published_at,result_first_observed_at FROM annual_time_evidence').fetchone(),
                ('2025-05-17T14:16:01+09:00','2025-05-18T12:00:00+09:00','2025-05-18T12:01:00+09:00'))
            db.close()


if __name__ == '__main__':
    unittest.main()
