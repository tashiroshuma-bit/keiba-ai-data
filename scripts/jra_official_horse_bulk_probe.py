"""Bounded primary-source JRA result page probe for horse profile hyperlinks.

Research diagnostics only; does not infer IDs from JRA registration ledger serials.
Downloads at most four sample result pages and emits provenance. Real bulk crawl
requires an explicit source availability and rate-limit decision after the probe.
"""
import argparse
import hashlib
import json
import re
import time
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin, unquote, urlsplit

OFFICIAL=("https://www.jra.go.jp/JRADB/accessS.html?CNAME=pw01sde1006202301010420230105%2F7C",
          "https://www.jra.go.jp/JRADB/accessU.html?CNAME=pw01dud102019103827%2F73")
class HorseLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links=[]
    def handle_starttag(self,tag,attrs):
        if tag!="a":return
        attr=dict(attrs)
        href=attr.get("href","")
        if "pw01dud" in href or "accessU.html" in href:
            self.links.append(href)
def fetch(url):
    if not url.startswith("https://www.jra.go.jp/JRADB/"):
        raise ValueError("unapproved host")
    headers={"User-Agent":"Mozilla/5.0 (compatible; research horse ID provenance audit)",
             "Accept":"text/html,application/xhtml+xml"}
    req=urllib.request.Request(url,headers=headers)
    with urllib.request.urlopen(req,timeout=18) as resp:
        data=resp.read(3_000_001)
        status=resp.status
    if len(data)>3_000_000:raise ValueError("maximum source size exceeded")
    page=None
    for encoding in ("cp932","shift_jis","utf-8"):
        try:page=data.decode(encoding);break
        except UnicodeDecodeError:continue
    if page is None:page=data.decode("cp932",errors="replace")
    hp=HorseLinks();hp.feed(page)
    matches=[]
    for link in hp.links:
        abs_url=urljoin(url,link)
        m=re.search(r"pw01dud[0-9]+?([12][0-9]{9})(?:%2[fF]|/)",abs_url)
        if m:matches.append({"horse_id":"jra:"+m.group(1),"url":abs_url})
    return {"url":url,"status":status,"bytes":len(data),
            "sha256":hashlib.sha256(data).hexdigest(),
            "horse_links_found":len(hp.links),"id_links":matches[:12],
            "jra_profile_10digit_mentions":len(set(re.findall(r"20[0-9]{8}",page)))}
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",default="/tmp/jra_official_horse_probe.json")
    args=parser.parse_args()
    results=[]
    for i,url in enumerate(OFFICIAL):
        if i:time.sleep(1)
        try:results.append({"ok":True,**fetch(url)})
        except Exception as e:results.append({"ok":False,"url":url,"error":type(e).__name__+":"+str(e)[:260]})
    with open(args.output,"w") as out:json.dump({"probes":results},out,ensure_ascii=False,indent=2)
    print(json.dumps({"probes":results},ensure_ascii=False)[:5000])
if __name__=="__main__":main()
