"""Build a closed, verified DB and immutable source ZIP for ordered saving."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'keiba_v48'))
from annual_year_update import update,digest
from integrated_data_audit import audit_database


def build(base,stage,originals,catalog,votes):
    stage=Path(stage)
    if stage.exists():raise ValueError('fresh checkpoint directory required')
    stage.mkdir(parents=True)
    database=stage/'jra_2023_2025.sqlite'
    report=update(base,database,2026)
    (stage/'update.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    audit=audit_database(database,2,False)
    (stage/'data_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2))
    with sqlite3.connect(database.resolve().as_uri()+'?mode=ro',uri=True) as c:
        assert c.execute('pragma integrity_check').fetchall()==[('ok',)]
        assert not c.execute('pragma foreign_key_check').fetchall()
        c.row_factory=sqlite3.Row
        docs=[dict(r) for r in c.execute('select * from annual_report_documents where year=2026 order by url')]
    archive=stage/'jra_pdf_2026_checkpoint_20261020.zip'
    manifest=dict(schema='jra-2026-official-originals-v1',checkpoint_observed_at=dt.datetime.now(dt.timezone.utc).isoformat(),
                  documents=docs,additional_sources=[],historical_publication_times='unknown; never PDF metadata')
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for d in docs:
            p=Path(d['local_path']);assert digest(p)==d['sha256']
            z.write(p,'pdf/'+p.name)
        z.write(Path(originals)/'2026.html','2026.html')
        for folder,prefix in ((catalog,'catalog'),(votes,'votes')):
            for p in sorted(Path(folder).rglob('*')):
                if p.is_file() and p.suffix in ('.pdf','.bin','.json'):
                    z.write(p,prefix+'/'+p.name)
                    manifest['additional_sources'].append(dict(path=prefix+'/'+p.name,bytes=p.stat().st_size,sha256=digest(p)))
        z.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2))
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert len([n for n in z.namelist() if n.startswith('pdf/')])==234
    result=dict(database=dict(path=str(database.resolve()),bytes=database.stat().st_size,sha256=digest(database)),
                originals=dict(path=str(archive.resolve()),bytes=archive.stat().st_size,sha256=digest(archive)),
                update_report=str((stage/'update.json').resolve()),audit_report=str((stage/'data_audit.json').resolve()))
    (stage/'checkpoint.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for option in ('base','stage','originals','catalog','votes'):ap.add_argument('--'+option,required=True)
    a=ap.parse_args();build(a.base,a.stage,a.originals,a.catalog,a.votes)
