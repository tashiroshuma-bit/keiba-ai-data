"""Discover 2026 JRA official race-result CNAME seeds from verified profiles.

Never construct checksum suffixes or accept non-JRA original links. Archives
all downloaded profile pages and emits an evidence-marked week seed catalog.
"""
import argparse
import collections
import hashlib
import json
import re
import time
import urllib.request
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit, unquote
from scripts.jra_official_race_bulk_id_crawler import approved_result_url, race_id_from_url, save_exclusive

class OfficialHistoryLinks(HTMLParser):
    def __init__(self, base):
        super().__init__()
        self.base = base
        self.links = []
    def handle_starttag(self, tag, attrs):
        if tag != 'a':
            return
        href = dict(attrs).get('href')
        if href:
            url = urljoin(self.base, href)
            if approved_result_url(url):
                self.links.append(url)


def official_date(url):
    from scripts.jra_official_race_bulk_id_crawler import RESULT_RE
    m = RESULT_RE.search(unquote(url))
    return date.fromisoformat(m.group(6)[:4]+'-'+m.group(6)[4:6]+'-'+m.group(6)[6:8]) if m else None


def discover(profiles_manifest, output_dir, *, year=2026, max_profiles=60,
             delay=1.5):
    root=Path(output_dir)
    if root.exists() and any(root.iterdir()):
        raise FileExistsError('original source folder must be new')
    root.mkdir(parents=True, exist_ok=True)
    profiles=json.loads(Path(profiles_manifest).read_text(encoding='utf-8'))['profiles']
    if delay < 1 or max_profiles<1:
        raise ValueError('rate limit or max profiles invalid')
    seeds={}
    inspections=[]
    for index,p in enumerate(profiles[:max_profiles]):
        url=p['official_profile_url']
        if urlsplit(url).hostname!='www.jra.go.jp' or urlsplit(url).scheme!='https' or urlsplit(url).path!='/JRADB/accessU.html':
            raise ValueError('non-JRA official profile')
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (compatible; historical source audit)','Accept':'text/html'})
            with urllib.request.urlopen(req, timeout=20) as res:
                if res.status!=200:raise ValueError('non-200')
                raw=res.read(2_000_001)
            if len(raw)>2_000_000:raise ValueError('source too large')
            sha=hashlib.sha256(raw).hexdigest()
            save_exclusive(root/'raw'/f'{sha}.bin',raw)
            text=None
            for codec in ('cp932','shift_jis','utf-8'):
                try:text=raw.decode(codec);break
                except UnicodeDecodeError:pass
            if text is None:text=raw.decode('cp932',errors='replace')
            parser=OfficialHistoryLinks(url)
            parser.feed(text)
            candidates=[]
            for result_url in parser.links:
                d=official_date(result_url)
                if d is None or d.year!=year:continue
                yr,wk,_=d.isocalendar()
                seeds.setdefault((yr,wk), {'iso_year':yr,'iso_week':wk,'seed_url':result_url,
                                             'seed_source_profile_url':url,'source_sha256':sha,
                                             'source_name':p['horse_name']})
                candidates.append(result_url)
            inspections.append({'profile_name':p['horse_name'],'success':True,'sha256':sha,
                                'source_url':url,'total_race_result_links':len(parser.links),
                                'target_year_links':len(candidates),'sample_links':candidates[:4],
                                'observed_at':datetime.now(timezone.utc).isoformat()})
        except Exception as e:
            inspections.append({'profile_name':p['horse_name'],'success':False,
                                'source_url':url,'error':type(e).__name__+':'+str(e)[:250]})
        if index + 1 < min(max_profiles,len(profiles)):time.sleep(delay)
    catalog={'schema':'jra-2026-profile-history-result-week-seeds-v1',
             'source':'JRA official primary profile race-history links; SHA archived',
             'known_seed_weeks':len(seeds), 'rows':list(sorted(seeds.values(),key=lambda r:(r['iso_year'],r['iso_week']))),
             'profiles_attempted':len(inspections), 'inspections':inspections}
    (root/'discovered_weeks.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return {'profile_attempts':len(inspections),'profile_success':sum(1 for x in inspections if x['success']),
            'year':year,'year_weeks_discovered':len(seeds),
            'race_result_links':sum(x.get('target_year_links',0) for x in inspections)}

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--profiles',required=True)
    p.add_argument('--output-dir',required=True)
    p.add_argument('--year',type=int,default=2026)
    p.add_argument('--max-profiles',type=int,default=60)
    p.add_argument('--delay',type=float,default=1.5)
    a=p.parse_args()
    print(json.dumps(discover(a.profiles,a.output_dir,year=a.year,
                              max_profiles=a.max_profiles,delay=a.delay),ensure_ascii=False))