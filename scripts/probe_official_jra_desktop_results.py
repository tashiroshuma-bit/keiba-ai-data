"""Probe JRA official DESKTOP result page for all-runner historical data.

No automated use of third-party websites. Extract a small diagnostic sample
from one JRA-hosted race and classify links, without inventing horse IDs.
"""
import hashlib,json,re,datetime
from urllib.request import urlopen,Request
from bs4 import BeautifulSoup
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
URL="https://www.jra.go.jp/JRADB/accessS.html?CNAME=pw01sde0108202605021220261108%2FB4"
OUT=ROOT/"operations/data_updates/jra_desktop_result_html_probe_20261108.json"

def main():
    with urlopen(Request(URL,headers={"User-Agent":"Mozilla/5.0","Accept-Language":"ja,en;q=0.8"}),timeout=25) as stream:
        raw=stream.read()
    soup=BeautifulSoup(raw,"html.parser")
    text=soup.get_text(" ",strip=True)
    tables=[]
    for table in soup.select("table"):
        header=[c.get_text(" ",strip=True) for c in table.select("th")[:28]]
        rows=[]
        for tr in table.select("tr"):
            cells=tr.find_all(["th","td"],recursive=False)
            values=[c.get_text(" ",strip=True) for c in cells]
            if not cells:continue
            links=[{"text":a.get_text(" ",strip=True)[:35],"url":a.get("href","")[:160]}
                for a in tr.select("a[href]")[:4]]
            rows.append({"values":values[:16],"links":links})
            if len(rows)>=5:break
        if header or rows:
            tables.append({"header":header,"first_rows":rows})
    nav=[]
    for a in soup.select("a[href]"):
        href=a.get("href","")
        if "sde" in href or "dud00" in href:
            nav.append({"text":a.get_text(" ",strip=True)[:45],"href":href[:210]})
    output={"source_url":URL,"sha256":hashlib.sha256(raw).hexdigest(),
        "observed_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "bytes":len(raw),"title":soup.title.get_text(" ",strip=True) if soup.title else None,
        "date_present":"2026年11月8日" in text,
        "kyoto_present":"京都" in text,
        "has_jra_horse_profile_links":bool(re.search(r"pw01dud10\d{10}",raw.decode("utf-8","ignore"))),
        "table_count":len(tables),"table_samples":tables[:12],
        "navigation":nav[:100],"navigation_count":len(nav),
        "html_start":str(soup.get_text(" ",strip=True)[:500])}
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(output,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({k:output[k] for k in ("bytes","date_present","kyoto_present",
        "has_jra_horse_profile_links","table_count","html_start")},ensure_ascii=False))
if __name__=="__main__":main()
