"""Rate-limited exact JRA race result -> 10 digit horse ID crawler.

Public official race pages link each `<tr>` horse number/name to a JRA profile.
This crawler saves original response bytes (SHA256-addressed), race/horse link
rows, errors and next-page URLs. No guesswork or mutation of canonical SQLite.
Only the explicit --max-pages bound is fetched in each invocation.
"""
import argparse
import collections
import hashlib
import json
import os
import re
import time
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, unquote, urlsplit
from datetime import datetime, timezone

RESULT_RE=re.compile(r"pw01sde10([0-9]{2})(20[0-9]{2})([0-9]{2})([0-9]{2})([0-9]{2})(20[0-9]{6})/(?:[0-9A-F]{2})",re.I)
HORSE_RE=re.compile(r"pw01dud[0-9]*?(20[0-9]{8})/(?:[0-9A-F]{2})",re.I)
HOST="www.jra.go.jp"

def race_id_from_url(url):
    m=RESULT_RE.search(unquote(url))
    if m is None:return None
    venue,year,meeting,day,race,calendar=m.groups()
    if calendar[:4]!=year:return None
    return year+venue+meeting+day+race

def approved_result_url(url):
    p=urlsplit(url)
    return p.scheme=="https" and p.hostname==HOST and p.path=="/JRADB/accessS.html" and race_id_from_url(url) is not None

def clean_name(value):
    import unicodedata
    return "".join(unicodedata.normalize("NFKC",value).split())

class OfficialRaceParser(HTMLParser):
    def __init__(self,base_url):
        super().__init__(convert_charrefs=True)
        self.base=base_url;self.depth=0;self.cells=[];self.active=None
        self.runners=[];self.other_races=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=="tr":
            self.depth+=1
            if self.depth==1:self.cells=[];self.active=None
        if tag=="td" and self.depth==1:
            self.cells.append({"text":"","profiles":[]});self.active=self.cells[-1]
        if tag=="a" and attrs.get("href"):
            href=urljoin(self.base,attrs["href"])
            if tag=="a" and approved_result_url(href):self.other_races.append(href)
            if self.active is not None:
                m=HORSE_RE.search(unquote(href))
                if m and urlsplit(href).hostname==HOST:
                    self.active["profiles"].append({"horse_id":"jra:"+m.group(1),"url":href})
    def handle_data(self,data):
        if self.active is not None:self.active["text"]+=data
    def handle_endtag(self,tag):
        if tag=="td" and self.depth==1:self.active=None
        if tag=="tr" and self.depth:
            self.depth-=1
            if self.depth==0:
                cells=self.cells
                if len(cells)>=4:
                    profiles=cells[3]["profiles"]
                    num=cells[2]["text"].strip()
                    name=clean_name(cells[3]["text"])
                    if len(profiles)==1 and num.isdigit() and 1<=int(num)<=30 and name:
                        self.runners.append({"horse_number":int(num),"horse_name":name,
                            "horse_id":profiles[0]["horse_id"],
                            "profile_url":profiles[0]["url"]})
                self.active=None;self.cells=[]

def parse_html(data,url):
    page=None
    for enc in ("cp932","shift_jis","utf-8"):
        try:page=data.decode(enc);break
        except UnicodeDecodeError:continue
    if page is None:page=data.decode("cp932",errors="replace")
    parser=OfficialRaceParser(url)
    parser.feed(page)
    rows=parser.runners
    if len(rows)<3:raise ValueError("official result page yielded fewer than three horse-ID rows")
    if len({r["horse_number"] for r in rows})!=len(rows):raise ValueError("duplicate horse number")
    if len({r["horse_id"] for r in rows})!=len(rows):raise ValueError("duplicate horse profile ID")
    return rows,sorted(set(parser.other_races))

def save_exclusive(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(str(path),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,"wb") as out:out.write(data)

def run(seeds,output_dir,*,max_pages=12,delay=1.0,year_min=2023,year_max=2026):
    if not 1<=max_pages<=500:raise ValueError("max_pages 1..500")
    if delay<1:raise ValueError("at least 1s between requests")
    root=Path(output_dir)
    if root.exists() and any(root.iterdir()):
        raise FileExistsError("use an empty output folder; do not overwrite evidence")
    root.mkdir(parents=True,exist_ok=True)
    queue=collections.deque(seeds)
    seen=set();records=[];failures=[]
    while queue and len(seen)<max_pages:
        url=queue.popleft()
        rid=race_id_from_url(url)
        if not approved_result_url(url) or rid in seen or not year_min<=int(rid[:4])<=year_max:continue
        seen.add(rid)
        try:
            req=urllib.request.Request(url,headers={
                "User-Agent":"Mozilla/5.0 (compatible; research JRA official horse-ID verification)",
                "Accept":"text/html,application/xhtml+xml"})
            with urllib.request.urlopen(req,timeout=20) as response:
                if response.status!=200:raise ValueError("non 200 result page")
                data=response.read(2_000_001)
            if len(data)>2_000_000:raise ValueError("oversized official source")
            horse_rows,nearby=parse_html(data,url)
            digest=hashlib.sha256(data).hexdigest()
            save_exclusive(root/"raw"/(digest+".bin"),data)
            records.append({"race_id":rid,"source_url":url,"source_sha256":digest,
                "observed_at":datetime.now(timezone.utc).isoformat(),
                "horses":horse_rows})
            for dest in nearby:
                nxt=race_id_from_url(dest)
                if nxt not in seen and year_min<=int(nxt[:4])<=year_max:queue.append(dest)
        except Exception as ex:
            failures.append({"race_id":rid,"source_url":url,
                             "reason":type(ex).__name__+":"+str(ex)[:180]})
        if queue and len(seen)<max_pages:time.sleep(delay)
    manifest={"schema":"jra-official-raw-results-horse-id-recovery-v1",
              "downloaded_races":len(records),"attempted_races":len(seen),
              "horse_rows":sum(len(r["horses"]) for r in records),
              "discovered_pending_race_links":len(queue),
              "records":records,"failures":failures,
              "not_joined_to_canonical_db":True}
    save_exclusive(root/"official_race_horse_ids.json",
                   (json.dumps(manifest,ensure_ascii=False,indent=2)+"\n").encode())
    return {"attempted":len(seen),"success":len(records),
            "horse_rows":manifest["horse_rows"],"failed":len(failures),
            "pending_links":len(queue),"saved":str(root/"official_race_horse_ids.json")}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--seed",action="append",required=True)
    p.add_argument("--output-dir",required=True)
    p.add_argument("--max-pages",type=int,default=12)
    p.add_argument("--delay",type=float,default=1.0)
    a=p.parse_args()
    print(json.dumps(run(a.seed,a.output_dir,max_pages=a.max_pages,delay=a.delay),
                     ensure_ascii=False))
if __name__=="__main__":main()
