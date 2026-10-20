import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from annual_reports import connect
from annual_year_update import raw_history_digest
from public_catalog import get


class IncrementalEvidenceTests(unittest.TestCase):
    def test_earlier_outcomes_are_immutable_but_identity_is_separate(self):
        with tempfile.TemporaryDirectory() as root:
            db=connect(str(Path(root)/'a.sqlite'))
            db.execute("insert into annual_report_documents(url,year,venue,meeting,day,status) values('pdf',2025,'tokyo',1,1,'parsed')")
            db.execute("insert into annual_report_races(race_id,document_url,page_number,panel,race_number,status,issues_json,metadata_json) values('202501010101','pdf',1,0,1,'validated_result','[]','{}')")
            payload=dict(finish_position=1,horse_id=None,jockey_id=None,identity_status='unlinked')
            db.execute('insert into annual_report_runners(race_id,horse_number,finish_order,payload_json) values(?,1,1,?)',('202501010101',json.dumps(payload)))
            before=raw_history_digest(db,2026)
            payload.update(horse_id='jra:1234567890',identity_status='linked')
            db.execute('update annual_report_runners set payload_json=?',(json.dumps(payload),))
            self.assertEqual(before,raw_history_digest(db,2026))
            payload['finish_position']=2
            db.execute('update annual_report_runners set payload_json=?',(json.dumps(payload),))
            self.assertNotEqual(before,raw_history_digest(db,2026));db.close()

    def test_public_catalog_does_not_substitute_protected_profile_routes(self):
        with tempfile.TemporaryDirectory() as root:
            for url in ('https://www.jra.go.jp/JRADB/accessS.html','https://www.jra.go.jp/JRADB/accessU.html','https://www.jbis.or.jp/'):
                with self.assertRaises(ValueError):get(url,root)

    def test_cached_refusal_and_corrupt_evidence_do_not_trigger_network(self):
        with tempfile.TemporaryDirectory() as root:
            url='https://www.jra.go.jp/datafile/resist/'
            stem=Path(root)/hashlib.sha256(url.encode()).hexdigest()
            stem.with_suffix('.json').write_text(json.dumps(dict(url=url,http_status=403)))
            with patch('public_catalog.fetch',side_effect=AssertionError('network')):
                with self.assertRaises(PermissionError):get(url,root)
            stem.with_suffix('.json').write_text(json.dumps(dict(url=url,http_status=200,sha256='0'*64)))
            stem.with_suffix('.bin').write_bytes(b'altered')
            with patch('public_catalog.fetch',side_effect=AssertionError('network')):
                with self.assertRaisesRegex(ValueError,'hash mismatch'):get(url,root)


if __name__=='__main__':unittest.main()
