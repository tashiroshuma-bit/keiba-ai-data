"""Inspect one JRA official horse profile for pedigree and prior result structure."""
import hashlib,json,datetime
from urllib.request import Request,urlopen
from bs4 import BeautifulSoup
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
URL="https://www.jra.go.jp/JRADB/accessU.html?CNAME=pw01dud002021103488/F3"
OUT=ROOT/"operations/data_updates/jra_official_horse_profile_html_probe_20261108.json"
def main():
    with urlopen(Request(URL,headers={"User-Agent":"Mozilla/5.0"}),timeout=25) as stream:
        raw=stream.read()
    soup=BeautifulSoup(raw,"html.parser")
    out={"url":URL,"source_sha256":hashlib.sha256(raw).hexdigest(),
         "observed_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),
         "bytes":len(raw),
         "title":soup.title.get_text(" ",strip=True) if soup.title else None,
         "contains_sire":("父" in soup.get_text(" ",strip=True)),
         "contains_dam":("母" in soup.get_text(" ",strip=True)),
         "contains_past_results":("競走成績" in soup.get_text(" ",strip=True)),
         "tables":[]}
    for table in soup.select("table")[:16]:
        rows=[]
        for tr in table.select("tr")[:6]:
            cells=[c.get_text(" ",strip=True)[:100] for c in tr.find_all(["td","th"],recursive=False)]
            if cells:rows.append(cells)
        out["tables"].append(rows)
    out["body_sample"]=soup.get_text(" ",strip=True)[800:2200]
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({k:out[k] for k in ("bytes","title","contains_sire","contains_dam","contains_past_results")},ensure_ascii=False))
if __name__=="__main__":main()
