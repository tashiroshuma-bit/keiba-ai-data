"""Create an auditable *research* overlay for JRA's 1,975 reviewed races.

Does not mutate source canonical v12 or initial review grade overlay. The nine
whole-race cancellations must be evidenced by the original, SHA-checked JRA PDF;
PDF glyph extraction errors are allowed only if exact official runner name matches
once the repeating glyph artifact is deterministically removed. One foreign name
must be corroborated by official independent JRA horse profile and race rank.
"""
import argparse, hashlib, json, re, shutil, sqlite3, zipfile
from pathlib import Path

FOREIGN = {
    'race_id':'202405050812','horse_number':13,
    'expected_original':'ファンタスティックムーン',
    'screen_truncated_name':'ファンタスティック',
    'official_horse_id':'jra:2020190004',
    'official_rank':11,'official_body_weight':440,
    'official_profile_url':'https://www.jra.go.jp/JRADB/accessU.html?CNAME=pw01dud102020190004%2FAF',
    'official_results_url':'https://www.jra.go.jp/datafile/seiseki/g1/jc/result/jc2024.html'
}
OFFICIAL_META={
    'race_id':'202301020407','race_date':'2023-08-20','track':'札幌',
    'surface':'turf','distance_m':2000,'expected_runners':16,
    'official_url':'https://www.jra.go.jp/JRADB/accessS.html?CNAME=pw01sde1001202302040720230820%2F13'
}

def digest(data):return hashlib.sha256(data).hexdigest()

def iso_name(name):
    # Only applied to one original PDF race whose extraction repeats every glyph
    # four times. Always compare output to *official* complete horse name.
    return re.sub(r'(.)\1{3}',r'\1',name)

def run(db,old_overlay,original_pdf_zip,original_pdf_audit,output,report):
    db=Path(db);old_overlay=Path(old_overlay);output=Path(output)
    for p in [db,old_overlay,original_pdf_zip,original_pdf_audit]:
        if not Path(p).is_file():raise FileNotFoundError(p)
    if output.exists():raise FileExistsError(output)
    pdf=json.loads(Path(original_pdf_audit).read_text())
    assert pdf['race_rows']==9 and pdf['distinct_official_original_pdfs']==5
    with zipfile.ZipFile(original_pdf_zip) as z:
        if z.testzip() is not None:raise ValueError('damaged original PDF evidence')
        for src in pdf['acquired'].values():
            if digest(z.read(src['stored_as']))!=src['sha256']:
                raise ValueError('official original PDF hash mismatch')
    shutil.copy2(old_overlay,output)
    dest=sqlite3.connect(output)
    canonical=sqlite3.connect('file:'+str(db.resolve())+'?mode=ro',uri=True)
    try:
        dest.execute('BEGIN IMMEDIATE')
        dest.execute('''CREATE TABLE IF NOT EXISTS reviewed_original_pdf_cancellations (
          race_id TEXT PRIMARY KEY, official_pdf_url TEXT NOT NULL, source_sha256 TEXT NOT NULL,
          official_original_pdf_verified INTEGER NOT NULL CHECK (official_original_pdf_verified=1),
          official_race_number_verified INTEGER NOT NULL CHECK (official_race_number_verified=1),
          note TEXT NOT NULL)''')
        for row in pdf['audits']:
            rid=row['race_id']; base=dest.execute('SELECT official_pdf_url FROM review_cancelled_race_evidence WHERE race_id=?',(rid,)).fetchone()
            if not base or base[0]!=row['url'] or not row['raw_sha_verified'] or not row['pymupdf_original_pdf_whole_race_cancel_verified'] or not row['pymupdf_original_pdf_race_number_verified']:
                raise ValueError('insufficient PDF proof '+rid)
            dest.execute('INSERT INTO reviewed_original_pdf_cancellations VALUES (?,?,?,?,?,?)',
                (rid,row['url'],row['source_sha256'],1,1,'Official PDF proves whole-race cancellation, not finish position'))
            dest.execute('UPDATE review_cancelled_race_evidence SET original_pdf_sha256_verified=1,evidence_grade=? WHERE race_id=?',
                ('ORIGINAL_JRA_PDF_SHA_AND_RACE_NUMBER_WHOLE_RACE_CANCEL_VERIFIED',rid))
        dest.execute('''CREATE TABLE IF NOT EXISTS reviewed_runner_name_reconciliation (
          race_id TEXT NOT NULL,horse_number INTEGER NOT NULL,original_pdf_name TEXT NOT NULL,
          official_result_name TEXT NOT NULL, official_horse_id TEXT NOT NULL,
          evidence_grade TEXT NOT NULL, official_source_sha256 TEXT NOT NULL,
          independent_official_profile_url TEXT,
          PRIMARY KEY (race_id,horse_number))''')
        namecases=list(dest.execute('''SELECT race_id,horse_number,horse_name_official,horse_id_official,
                    official_rank,official_status,source_sha256 FROM review_runner_evidence WHERE name_match=0'''))
        if len(namecases)!=10:raise ValueError('unexpected name-diff count')
        for rid,n,official,hid,rank,status,sha in namecases:
            src=canonical.execute('SELECT horse_name,finish_order,payload_json FROM annual_report_runners WHERE race_id=? AND horse_number=?',(rid,n)).fetchone()
            if not src or not hid or not re.fullmatch(r'jra:[0-9]{10}',hid):raise ValueError('missing canonical/official horse')
            orig,finish,payload=src
            if rid=='202307011012':
                if iso_name(orig)!=official or (rank is not None and finish!=rank) or (rank is None and status!='DNF'):raise ValueError('fourfold PDF name mismatch')
                grade='EXACT_OFFICIAL_RESULT_AFTER_FOURFOLD_PDF_GLYPH_DEDUP'
                profile=None
            elif (rid==FOREIGN['race_id'] and n==FOREIGN['horse_number'] and
                  orig==FOREIGN['expected_original'] and official==FOREIGN['screen_truncated_name'] and
                  hid==FOREIGN['official_horse_id'] and rank==FOREIGN['official_rank'] and
                  finish==rank and str(FOREIGN['official_body_weight']) in str(json.loads(payload).get('body_weight_raw'))):
                grade='OFFICIAL_JRA_HORSE_PROFILE_DATE_RANK_WEIGHT_CORROBORATED'
                profile=FOREIGN['official_profile_url']
            else:raise ValueError('unknown mismatch: '+rid+'/'+str(n))
            dest.execute('INSERT INTO reviewed_runner_name_reconciliation VALUES (?,?,?,?,?,?,?,?)',
                (rid,n,orig,official,hid,grade,sha,profile))
        dest.execute('''CREATE TABLE IF NOT EXISTS reviewed_race_metadata_reconciliation (
          race_id TEXT PRIMARY KEY,race_date TEXT NOT NULL,track TEXT NOT NULL,
          surface TEXT NOT NULL,distance_m INTEGER NOT NULL,field_size INTEGER NOT NULL,
          official_url TEXT NOT NULL,source_sha256 TEXT NOT NULL, evidence_grade TEXT NOT NULL)''')
        r=OFFICIAL_META;rid=r['race_id']
        actual=canonical.execute('SELECT track,surface,COUNT(*) FROM annual_report_races JOIN annual_report_runners USING(race_id) WHERE race_id=?',(rid,)).fetchone()
        if actual!=(r['track'],r['surface'],r['expected_runners']):raise ValueError('metadata mismatch')
        official=dest.execute('SELECT source_url,source_sha256,source_field_size FROM review_race_evidence WHERE race_id=?',(rid,)).fetchone()
        if not official or official[2]!=r['expected_runners']:raise ValueError('review result headcount mismatch')
        dest.execute('INSERT INTO reviewed_race_metadata_reconciliation VALUES (?,?,?,?,?,?,?,?,?)',
            (rid,r['race_date'],r['track'],r['surface'],r['distance_m'],r['expected_runners'],r['official_url'],official[1],
             'JRA_OFFICIAL_2023_08_20_SAPPORO_7R_PUBLISHED_METADATA'))
        dest.commit()
        checks={
         'original_review_races':dest.execute('SELECT COUNT(*) FROM review_race_evidence').fetchone()[0],
         'official_result_rows':dest.execute('SELECT COUNT(*) FROM review_runner_evidence').fetchone()[0],
         'cancelled_verified':dest.execute('SELECT COUNT(*) FROM reviewed_original_pdf_cancellations').fetchone()[0],
         'pdf_text_glyph_verified':dest.execute("SELECT COUNT(*) FROM reviewed_runner_name_reconciliation WHERE evidence_grade LIKE '%FOURFOLD%'").fetchone()[0],
         'foreign_profile_verified':dest.execute("SELECT COUNT(*) FROM reviewed_runner_name_reconciliation WHERE evidence_grade LIKE '%PROFILE%'").fetchone()[0],
         'race_metadata_verified':dest.execute('SELECT COUNT(*) FROM reviewed_race_metadata_reconciliation').fetchone()[0],
         'official_nonfinish':dest.execute("SELECT COUNT(*) FROM review_runner_evidence WHERE official_status<>'FINISHED'").fetchone()[0],
         'sqlite_check':dest.execute('PRAGMA quick_check').fetchone()[0],
         'fk_errors':len(dest.execute('PRAGMA foreign_key_check').fetchall())}
        if checks!={'original_review_races':1966,'official_result_rows':27154,'cancelled_verified':9,
                    'pdf_text_glyph_verified':9,'foreign_profile_verified':1,'race_metadata_verified':1,
                    'official_nonfinish':1511,'sqlite_check':'ok','fk_errors':0}:
            raise ValueError('unexpected checks '+str(checks))
    finally:
        canonical.close();dest.close()
    result={'schema':'jra-reviewed-1975-source-evidence-v2','source_canonical_sha256':digest(db.read_bytes()),
        'source_review_overlay_sha256':digest(old_overlay.read_bytes()),
        'pdf_original_zip_sha256':digest(Path(original_pdf_zip).read_bytes()),
        'overlay_sha256':digest(output.read_bytes()),'overlay_bytes':output.stat().st_size,'checks':checks,
        'scope':'research-grade official result labels; not a production model or training promotion',
        'foreign_profile':FOREIGN,'metadata':OFFICIAL_META}
    Path(report).write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--database',required=True);p.add_argument('--review-overlay',required=True)
    p.add_argument('--pdf-original-zip',required=True);p.add_argument('--pdf-original-audit',required=True)
    p.add_argument('--output',required=True);p.add_argument('--report',required=True)
    a=p.parse_args()
    d=run(a.database,a.review_overlay,a.pdf_original_zip,a.pdf_original_audit,a.output,a.report)
    print(json.dumps({'overlay_bytes':d['overlay_bytes'],'overlay_sha256':d['overlay_sha256'],'checks':d['checks']},ensure_ascii=False))