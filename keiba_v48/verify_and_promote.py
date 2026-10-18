"""Audit PDF extraction and promote only reviewed complete fields."""
import argparse, json
from jra_pdf_archive import dbconnect
from pdf_runner_parser import parse_runner_lines, validate

def audit(c):
    c.execute('CREATE TABLE IF NOT EXISTS extraction_audit(year INTEGER,race_key TEXT,source_pdf_url TEXT,parsed_count INTEGER,issues_json TEXT,stage TEXT,PRIMARY KEY(year,race_key))')
    docs=c.execute("SELECT d.year,d.race_key,d.url,d.extracted_text,r.winner FROM documents d JOIN races r ON r.year=d.year AND r.race_key=d.race_key WHERE d.status='text_extracted'").fetchall()
    report={'documents_checked':0,'ready_for_review':0,'rejected':0}
    for year,key,url,raw,winner in docs:
        rows,errors=parse_runner_lines(raw or '')
        issues=validate(rows)+[e['reason'] for e in errors]
        if not any(r['finish_position']==1 and r['horse_name'].replace(' ','')==winner.replace(' ','') for r in rows):issues.append('winner mismatch')
        stage='rejected' if issues else 'ready_for_review'
        c.execute('INSERT OR REPLACE INTO extraction_audit VALUES(?,?,?,?,?,?)',(year,key,url,len(rows),json.dumps(issues,ensure_ascii=False),stage))
        report['documents_checked']+=1;report[stage]+=1
    c.commit();return report

def promote(c,year,key,expected_count):
    if expected_count<2:raise ValueError('expected count required')
    source=c.execute("SELECT d.url,d.extracted_text,r.winner FROM documents d JOIN races r ON r.year=d.year AND r.race_key=d.race_key WHERE d.year=? AND d.race_key=? AND d.status='text_extracted'",(year,key)).fetchone()
    if not source:raise ValueError('PDF text unavailable')
    url,raw,winner=source;rows,errors=parse_runner_lines(raw)
    issues=validate(rows,expected_count)
    if errors:issues.append('ambiguous runner rows')
    if not any(r['finish_position']==1 and r['horse_name'].replace(' ','')==winner.replace(' ','') for r in rows):issues.append('winner mismatch')
    if issues:raise ValueError('; '.join(issues))
    with c:
        c.execute('DELETE FROM runner_results WHERE year=? AND race_key=?',(year,key))
        c.executemany('INSERT INTO runner_results(year,race_key,horse_number,horse_name,finish_position,jockey,odds,source_pdf_url,verification) VALUES(?,?,?,?,?,?,?,?,?)',[(year,key,r['horse_number'],r['horse_name'],str(r['finish_position']),r['jockey'],str(r['final_win_odds']),url,'reviewed_pdf_complete_field') for r in rows])
        c.execute("UPDATE extraction_audit SET stage='promoted' WHERE year=? AND race_key=?",(year,key))
    return len(rows)

def main():
    p=argparse.ArgumentParser();p.add_argument('--db',required=True);p.add_argument('--year',type=int);p.add_argument('--race-key');p.add_argument('--expected-count',type=int);a=p.parse_args()
    c=dbconnect(a.db);print(json.dumps(audit(c),ensure_ascii=False))
    if a.year or a.race_key or a.expected_count:
        if not (a.year and a.race_key and a.expected_count):raise SystemExit('promotion requires --year --race-key --expected-count')
        print('promoted:',promote(c,a.year,a.race_key,a.expected_count))
if __name__=='__main__':main()
