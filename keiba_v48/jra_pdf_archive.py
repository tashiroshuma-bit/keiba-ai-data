"""JRA 2023-2025 grade-race PDF archive with SQLite provenance.
Does NOT claim extracted runner rows until separately validated.
Usage: python jra_pdf_archive.py --db jra.sqlite --pdf-dir pdfs
Optional: --index-dir saved_indexes (offline HTML files named 2023.html, etc.)
"""
import argparse, datetime, hashlib, json, re, sqlite3, time
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from bs4 import BeautifulSoup

BASE="https://www.jra.go.jp/datafile/seiseki/replay/{year}/jyusyo.html"
SCHEMA="""
CREATE TABLE IF NOT EXISTS races(
 year INTEGER NOT NULL, race_key TEXT NOT NULL, race_date TEXT,
 race_name TEXT NOT NULL, venue TEXT, course TEXT, winner TEXT,
 pdf_url TEXT, result_url TEXT, index_url TEXT NOT NULL,
 PRIMARY KEY(year,race_key));
CREATE TABLE IF NOT EXISTS documents(
 url TEXT PRIMARY KEY, year INTEGER, race_key TEXT,
 sha256 TEXT, byte_count INTEGER, local_path TEXT, status TEXT,
 extracted_text TEXT, extraction_method TEXT, error TEXT,
 fetched_at TEXT);
CREATE TABLE IF NOT EXISTS runner_results(
 year INTEGER NOT NULL, race_key TEXT NOT NULL, horse_number INTEGER NOT NULL,
 horse_name TEXT NOT NULL, finish_position TEXT, jockey TEXT, odds TEXT,
 source_pdf_url TEXT NOT NULL, verification TEXT NOT NULL,
 PRIMARY KEY(year,race_key,horse_number));
"""
def dbconnect(p):
 c=sqlite3.connect(p);c.executescript(SCHEMA);return c
def fetch(url):
 req=Request(url,headers={"User-Agent":"ResearchArchive/1.0 (personal research)"})
 with urlopen(req,timeout=25) as f:return f.read()
def parse_index(html,year):
 soup=BeautifulSoup(html,"html.parser")
 table=next((t for t in soup.find_all("table") if "プレイバック" in t.get_text(" ",strip=True) and "レース名" in t.get_text(" ",strip=True)),None)
 if table is None:raise ValueError(f"{year}: official graded race table not found")
 out=[]
 for tr in table.find_all("tr"):
  cells=tr.find_all(["td"])
  if len(cells)<8:continue
  values=[c.get_text(" ",strip=True) for c in cells]
  if not re.search(r"G[ⅠⅡⅢI]{1,3}|Ｊ・Ｇ|J・G",values[1],re.I):continue
  links=[(a.get_text(" ",strip=True).lower(),urljoin(BASE.format(year=year),a.get("href",""))) for a in tr.find_all("a",href=True)]
  pdf=next((url for _,url in links if urlparse(url).path.lower().endswith(".pdf")),None)
  result=next((url for label,url in links if "結果" in label),None)
  date_match=re.search(r"(\d{1,2})月(\d{1,2})日",values[0])
  date=f"{year}-{int(date_match[1]):02}-{int(date_match[2]):02}" if date_match else None
  key=(urlparse(pdf).path.rsplit("/",1)[-1].removesuffix(".pdf") if pdf else hashlib.sha256(("|".join(values[:5])).encode()).hexdigest()[:12])
  out.append(dict(year=year,race_key=key,race_date=date,race_name=values[1],venue=values[2],course=values[4],winner=values[5],pdf_url=pdf,result_url=result,index_url=BASE.format(year=year)))
 if not out:raise ValueError(f"{year}: no race rows recognized")
 return out
def pdf_text(data):
 import io
 import pdfplumber
 with pdfplumber.open(io.BytesIO(data)) as pdf:
  return "\n\n".join(p.extract_text(layout=False) or "" for p in pdf.pages)
def ingest(c,years,index_dir,pdf_dir,download,delay):
 pdf_dir.mkdir(parents=True,exist_ok=True)
 stats={}
 for year in years:
  try:
   ip=index_dir/f"{year}.html" if index_dir else None
   html=ip.read_bytes() if ip and ip.exists() else fetch(BASE.format(year=year))
   rows=parse_index(html,year)
   c.executemany("""INSERT INTO races(year,race_key,race_date,race_name,venue,course,winner,pdf_url,result_url,index_url)
      VALUES(:year,:race_key,:race_date,:race_name,:venue,:course,:winner,:pdf_url,:result_url,:index_url)
      ON CONFLICT(year,race_key) DO UPDATE SET race_name=excluded.race_name,pdf_url=excluded.pdf_url""",rows)
   c.commit()
   stats[year]={"races":len(rows),"pdf_links":sum(bool(r["pdf_url"]) for r in rows),"pdf_downloaded":0,"pdf_errors":0}
   for r in rows:
    url=r["pdf_url"]
    if not url or not download:continue
    p=pdf_dir/str(year)/(r["race_key"]+".pdf");p.parent.mkdir(parents=True,exist_ok=True)
    try:
     if not p.exists():
      data=fetch(url)
      if not data.startswith(b"%PDF-"):raise ValueError("not a PDF")
      p.write_bytes(data)
      time.sleep(delay)
     else:data=p.read_bytes()
     raw=pdf_text(data)
     if len(raw.strip())<100:raise ValueError("PDF has insufficient selectable text; manual review needed")
     c.execute("""INSERT OR REPLACE INTO documents
      (url,year,race_key,sha256,byte_count,local_path,status,extracted_text,extraction_method,error,fetched_at)
      VALUES(?,?,?,?,?,?,?,?,?,?,?)""",(url,year,r["race_key"],hashlib.sha256(data).hexdigest(),len(data),str(p),"text_extracted",raw,"pdfplumber",None,datetime.datetime.now(datetime.timezone.utc).isoformat()))
     stats[year]["pdf_downloaded"]+=1
    except Exception as e:
     c.execute("""INSERT OR REPLACE INTO documents(url,year,race_key,status,error,fetched_at)
      VALUES(?,?,?,?,?,?)""",(url,year,r["race_key"],"error",str(e),datetime.datetime.now(datetime.timezone.utc).isoformat()))
     stats[year]["pdf_errors"]+=1
    c.commit()
  except Exception as e:stats[year]={"error":str(e)}
 return stats
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--db",default="jra_2023_2025.sqlite")
 p.add_argument("--pdf-dir",default="jra_pdfs")
 p.add_argument("--index-dir",default=None)
 p.add_argument("--no-download",action="store_true")
 p.add_argument("--delay",type=float,default=1.0)
 a=p.parse_args()
 c=dbconnect(a.db)
 stats=ingest(c,[2023,2024,2025],Path(a.index_dir) if a.index_dir else None,Path(a.pdf_dir),not a.no_download,a.delay)
 print(json.dumps(stats,ensure_ascii=False,indent=2))
 print("Verified runner rows:",c.execute("SELECT count(*) FROM runner_results WHERE verification='verified'").fetchone()[0])
if __name__=="__main__":main()
