"""Fast, resumable JRA archive download using existing index/parser and SQLite schema.
Rate limited and bounded parallelism; only public JRA official documents.
"""
import argparse, concurrent.futures, hashlib, json, sqlite3, time, datetime
from pathlib import Path
from jra_pdf_archive import BASE, fetch, parse_index, pdf_text, dbconnect

def fetch_pdf(job, folder):
    year,key,url=job
    path=folder/str(year)/(key+".pdf")
    path.parent.mkdir(parents=True,exist_ok=True)
    try:
        data=path.read_bytes() if path.exists() else fetch(url)
        if not data.startswith(b"%PDF-"): raise ValueError("invalid PDF signature")
        if not path.exists():path.write_bytes(data)
        raw=pdf_text(data)
        if len(raw.strip())<100: raise ValueError("no selectable text")
        return (url,year,key,hashlib.sha256(data).hexdigest(),len(data),str(path),"text_extracted",raw,"pdfplumber",None,datetime.datetime.now(datetime.timezone.utc).isoformat())
    except Exception as e:
        return (url,year,key,None,None,None,"error",None,None,str(e),datetime.datetime.now(datetime.timezone.utc).isoformat())

def run(db, folder, years=(2023,2024,2025), workers=2, index_dir=None, retry_errors=False):
    c=dbconnect(db)
    errors={}
    for year in years:
        try:
            file=Path(index_dir)/f"{year}.html" if index_dir else None
            html=file.read_bytes() if file and file.exists() else fetch(BASE.format(year=year))
            rows=parse_index(html,year)
            c.executemany("""INSERT INTO races(year,race_key,race_date,race_name,venue,course,winner,pdf_url,result_url,index_url)
                VALUES(:year,:race_key,:race_date,:race_name,:venue,:course,:winner,:pdf_url,:result_url,:index_url)
                ON CONFLICT(year,race_key) DO UPDATE SET race_name=excluded.race_name,pdf_url=excluded.pdf_url""",rows)
            c.commit()
        except Exception as e:errors[year]=str(e)
    jobs=[]
    for year,key,url in c.execute("SELECT year,race_key,pdf_url FROM races WHERE pdf_url IS NOT NULL ORDER BY year,race_key").fetchall():
        if year not in years:continue
        row=c.execute("SELECT status FROM documents WHERE url=?",(url,)).fetchone()
        if row and (row[0]=="text_extracted" or (row[0]=="error" and not retry_errors)):continue
        jobs.append((year,key,url))
    completed=0
    # Only the main thread writes SQLite; workers perform network/PDF work.
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futures=[ex.submit(fetch_pdf,job,Path(folder)) for job in jobs]
        for future in concurrent.futures.as_completed(futures):
            item=future.result()
            c.execute("""INSERT OR REPLACE INTO documents
            (url,year,race_key,sha256,byte_count,local_path,status,extracted_text,extraction_method,error,fetched_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)""",item)
            c.commit()
            completed+=1
    report={"years":list(years),"index_errors":errors,
        "races_indexed":c.execute("SELECT count(*) FROM races WHERE year IN (2023,2024,2025)").fetchone()[0],
        "pdf_text_extracted":c.execute("SELECT count(*) FROM documents WHERE status='text_extracted'").fetchone()[0],
        "pdf_errors":c.execute("SELECT count(*) FROM documents WHERE status='error'").fetchone()[0],
        "runner_rows":c.execute("SELECT count(*) FROM runner_results").fetchone()[0],
        "new_pdf_jobs":completed}
    c.close()
    return report
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--db",default="jra_2023_2025.sqlite")
    p.add_argument("--pdf-dir",default="jra_pdfs")
    p.add_argument("--index-dir")
    p.add_argument("--workers",type=int,default=2)
    p.add_argument("--retry-errors",action="store_true")
    a=p.parse_args()
    if not 1<=a.workers<=4:raise SystemExit("workers must be 1..4")
    print(json.dumps(run(a.db,a.pdf_dir,workers=a.workers,index_dir=a.index_dir,retry_errors=a.retry_errors),ensure_ascii=False,indent=2))
if __name__=="__main__":main()
