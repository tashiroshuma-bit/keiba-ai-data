"""Source-linked archive completion. Preserve bytes, verify race identities, never guess IDs."""
import argparse
import collections
import concurrent.futures as cf
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
from urllib.parse import urljoin
import unicodedata

from official_linkage import (BASE, SourceCache, official_url, parse_result, parse_html,
                              race_key, links, schema, attest, propagate, audit, unlinked_causes)
from annual_reports import VENUES

PARSER_VERSION = 'official-rich-v3'
IDENTITY_FIELDS = ('race_id','race_date','horse_number','horse_name','birth_year','horse_id',
                   'jockey_name','jockey_id','source_finish_position','result_page_off_at','horse_profile_url')
VOID_SOURCES = [
 ('202404030612','2024-08-25','新潟',12,'https://www.jra.go.jp/keiba/calendar2024/2024/8/0825.html'),
 ('202408060108','2024-11-02','京都',8,'https://www.jra.go.jp/keiba/calendar2024/2024/11/1102.html'),
 ('202505021109','2025-05-31','東京',9,'https://www.jra.go.jp/news/202505/053104.html')]


def class_info(text):
    s = unicodedata.normalize('NFKC', text).upper().replace(' ', '')
    for pattern, level, grade in ((r'G(?:III|3)(?!I)',4,'G3'),(r'G(?:II|2)(?!I)',5,'G2'),(r'G(?:I|1)(?!I)',6,'G1')):
        if re.search(pattern,s): return level,'graded',grade
    for name, level in [('3勝',3),('2勝',2),('1勝',1),('1600万',3),('1000万',2),('500万',1),('オープン',4),('OP',4),('未勝利',0),('新馬',0)]:
        if name in s: return level,'nongraded',None
    return None,'unknown',None


def text_at(node,selector):
    cell=node.select_one(selector)
    return cell.get_text(' ',strip=True) if cell else ''


def numeric(s):
    m=re.search(r'\d+(?:\.\d+)?',s.replace(',',''))
    return float(m[0]) if m else None


def parse_rich(soup,url,meta):
    identities=parse_result(soup,url)
    table=soup.select_one('table.basic.narrow-xy')
    title=text_at(table,'.race_title')+' '+ ' '.join(i.get('alt','') for i in table.select('.race_title img'))
    course=text_at(table,'.course')
    level,category,grade=class_info(title)
    if category=='unknown':
        for img in table.select('.race_title img'):
            m=re.search(r'g([123])\.',img.get('src',''),re.I)
            if m: level,category,grade=7-int(m[1]),'graded','G'+m[1]
    dist=re.search(r'([\d,]+)\s*メートル',course)
    surface='dirt' if 'ダート' in course else 'turf' if '芝' in course else None
    if '障害' in title or 'ジャンプ' in title or '障害' in course: surface='jump'
    ground=text_at(table,'.condition .ground') or text_at(table,'.ground') or text_at(table,'.weather_ground') or text_at(table,'.date_line .baba')
    going=next((v for v in ('不良','稍重','重','良') if v in ground),None)
    by_number={r['horse_number']:dict(r) for r in identities}
    for tr in table.select('tbody > tr'):
        num=text_at(tr,'td.num')
        if not num.isdigit() or int(num) not in by_number: continue
        r=by_number[int(num)]; place=text_at(tr,'td.place')
        r['runner_status']=('nonstarter' if any(v in place for v in ('取消','除外')) else
                            'nonfinisher' if any(v in place for v in ('中止','失格')) else
                            'finished' if place.isdigit() else 'unknown')
        tm=re.search(r'(\d+):(\d+\.\d+)',text_at(tr,'td.time'))
        r['finish_time_seconds']=60*int(tm[1])+float(tm[2]) if tm else None
        r['finish_position']=r['source_finish_position']
        r['carried_weight']=numeric(text_at(tr,'td.weight'))
        r['last_3f_seconds']=numeric(text_at(tr,'td.f_time'))
        corner=next((li for li in tr.select('td.corner li[title]') if '4コーナー' in li['title']),None)
        r['corner4_position']=int(corner.get_text()) if corner and corner.get_text().isdigit() else None
        gate=tr.select_one('td.waku img[alt]'); gm=re.search(r'枠(\d+)',gate['alt']) if gate else None
        r['gate']=int(gm[1]) if gm else None
        r.update(class_level=level,race_category=category,grade=grade,distance_m=int(dist[1].replace(',','')) if dist else None,
                 surface=surface,going=going,track=next((v[1] for v in VENUES.values() if v[0]==r['race_id'][4:6]),None),
                 off_timestamp=r['result_page_off_at'])
    rows=sorted(by_number.values(),key=lambda r:r['horse_number'])
    active=[r for r in rows if r.get('runner_status')!='nonstarter']
    times=[r['finish_time_seconds'] for r in active if r.get('finish_time_seconds') is not None]
    mean=sum(times)/len(times) if times else 0
    sd=math.sqrt(sum((x-mean)**2 for x in times)/len(times)) if times else 0
    closing=[r['last_3f_seconds'] for r in active if r.get('last_3f_seconds') is not None]
    for r in rows:
        t=r.get('finish_time_seconds'); f=r.get('last_3f_seconds')
        r.update(field_size=len(active),margin_seconds=max(0,t-min(times)) if t is not None and times else None,
                 relative_speed_z=(mean-t)/sd if t is not None and sd else None,
                 last_3f_rank=1+sum(x<f for x in closing) if f is not None else None)
    payouts={}
    for dl in soup.select('dl'):
        heading=text_at(dl,'dt').replace(' ','')
        kind={'単勝':'win','ワイド':'wide','3連複':'trio','３連複':'trio'}.get(heading)
        if not kind: continue
        for line in dl.select('dd .line'):
            ns=re.findall(r'\d+',text_at(line,'.num'))
            yen=re.sub(r'\D','',text_at(line,'.yen'))
            if ns and yen:
                payouts[kind+':'+','.join(map(str,sorted(map(int,ns))))]=int(yen)
    ranks=[r['finish_position'] for r in active if r.get('finish_position')]
    displayed=[tr for tr in table.select('tbody > tr') if text_at(tr,'td.num').isdigit()]
    complete=(len(displayed)==len(rows) and len(active)>=3 and len(ranks)>=3 and sorted(ranks)==list(range(1,len(ranks)+1)) and
              all(r.get('runner_status') in ('finished','nonfinisher') and r.get('distance_m') and r.get('surface') and r.get('off_timestamp') for r in active))
    return dict(race_id=identities[0]['race_id'],race_date=identities[0]['race_date'],title=title,
                status='complete' if complete else 'exceptional_or_incomplete',runners=rows,
                active_horse_numbers=[r['horse_number'] for r in active],payouts=payouts,
                source_url=meta['url'],source_sha256=meta['sha256'],observed_at=meta['observed_at'],parser_version=PARSER_VERSION)


def crawl(cache_path,seed_urls,max_pages=12000,max_profiles=128,workers=4):
    if not 1<=workers<=4: raise ValueError('workers must be 1..4')
    cache=SourceCache(cache_path,'lxml'); queue=collections.deque();queued=set();seen=set();profiles=set();errors=[]
    for u in seed_urls:
        u=official_url(u)
        if u not in queued: queue.append(u);queued.add(u)
    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
        while queue and len(seen)<max_pages:
            batch=[]
            while queue and len(batch)<workers and len(seen)<max_pages:
                u=queue.popleft()
                if u not in seen:seen.add(u);batch.append(u)
            for u, future in zip(batch,[pool.submit(cache.get,u) for u in batch]):
                try:
                    soup,meta=future.result()
                    if race_key(u) and len(profiles)<max_profiles:
                        for a in soup.select('td.horse a[href]'):
                            p=official_url(urljoin(BASE,a['href']))
                            if p not in queued and len(profiles)<max_profiles:
                                profiles.add(p);queued.add(p);queue.appendleft(p)
                    for link in links(soup,u):
                        key=race_key(link)
                        if key and key[0][:4] in ('2023','2024','2025') and link not in queued:
                            queued.add(link);queue.append(link)
                except PermissionError:raise
                except Exception as e: errors.append({'url':u,'error':str(e)})
            if len(seen)%100==0: print(json.dumps(dict(processed=len(seen),remaining=len(queue),profiles=len(profiles))),flush=True)
    report=dict(processed=len(seen),remaining=len(queue),profiles=len(profiles),errors=errors)
    (Path(cache_path)/'crawl_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    return report


def read_result(path):
    meta=json.loads(path.read_text()); u=meta.get('url','')
    if not race_key(u):return None
    raw=path.with_suffix('.html').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=meta['sha256']: raise ValueError('cache checksum mismatch')
    try:return parse_rich(parse_html(raw,'lxml'),u,meta)
    except ValueError as e:return dict(error=str(e),meta=meta)


def rebuild(base,destination,cache_path):
    dest=Path(destination)
    if dest.exists():raise ValueError('new destination required')
    src=sqlite3.connect('file:'+str(Path(base).resolve())+'?mode=ro',uri=True)
    if src.execute('pragma integrity_check').fetchall()!=[('ok',)]:raise ValueError('invalid base')
    db=sqlite3.connect(':memory:');src.backup(db);src.close();schema(db)
    db.executescript('CREATE TABLE IF NOT EXISTS enriched_results(race_id TEXT PRIMARY KEY,status TEXT NOT NULL,payload_json TEXT NOT NULL); CREATE TABLE IF NOT EXISTS official_void_races(race_id TEXT PRIMARY KEY,reason TEXT,source_url TEXT,source_sha256 TEXT,observed_at TEXT);')
    paths=[p for p in Path(cache_path).glob('*.json') if race_key(json.loads(p.read_text()).get('url',''))]
    with cf.ProcessPoolExecutor(max_workers=4) as pool:
        for start in range(0,len(paths),32):
            for rich in pool.map(read_result,paths[start:start+32]):
                if 'error' in rich:
                    m=rich['meta']; db.execute('INSERT OR REPLACE INTO official_linkage_pages VALUES(?,?,?,?,?,?)',(m['url'],m['sha256'],m['observed_at'],'error',rich['error'],0));continue
                meta=dict(url=rich['source_url'],sha256=rich['source_sha256'],observed_at=rich['observed_at'])
                rows=[{k:r.get(k) for k in IDENTITY_FIELDS} for r in rich['runners']]
                matched=attest(db,rows,meta)
                db.execute('INSERT OR REPLACE INTO enriched_results VALUES(?,?,?)',(rich['race_id'],rich['status'],json.dumps(rich,ensure_ascii=False,separators=(',',':'))))
                db.execute('INSERT OR REPLACE INTO official_linkage_pages VALUES(?,?,?,?,?,?)',(meta['url'],meta['sha256'],meta['observed_at'],'matched',None,matched))
            if start%320==0: print(json.dumps({'rebuilt_pages':min(start+32,len(paths))}),flush=True)
    cache=SourceCache(cache_path,'lxml')
    for rid,date,track,num,url in VOID_SOURCES:
        stem=cache.folder/hashlib.sha256(url.encode()).hexdigest()
        if not stem.with_suffix('.html').exists():continue
        soup,meta=cache.get(url); text=re.sub(r'\s+','',unicodedata.normalize('NFKC',soup.get_text()))
        y,m,d=map(int,date.split('-'))
        if f'{y}年{m}月{d}日' not in text or not re.search(track+r'競馬.{0,5}第'+str(num)+r'レース.{0,10}取りやめ',text):raise ValueError('void evidence mismatch')
        db.execute('INSERT OR REPLACE INTO official_void_races VALUES(?,?,?,?,?)',(rid,'official_race_cancelled',url,meta['sha256'],meta['observed_at']))
    report=propagate(db);report.update(audit(db));report['unlinked_causes']=unlinked_causes(db)
    report['enriched_statuses']=dict(db.execute('select status,count(*) from enriched_results group by status'))
    report['missing_result_or_void_races']=[r[0] for r in db.execute('select race_id from annual_report_races where race_id not in(select race_id from enriched_results) and race_id not in(select race_id from official_void_races)')]
    report['void_races']=[r[0] for r in db.execute('select race_id from official_void_races')]
    db.commit();db.execute('VACUUM');dest.parent.mkdir(parents=True,exist_ok=True)
    target=sqlite3.connect(dest);db.backup(target);target.close();db.close()
    check=sqlite3.connect('file:'+str(dest.resolve())+'?mode=ro',uri=True)
    if check.execute('pragma integrity_check').fetchall()!=[('ok',)] or check.execute('pragma foreign_key_check').fetchall():raise ValueError('written archive failed validation')
    check.close();return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['crawl','rebuild']);p.add_argument('--cache',required=True);p.add_argument('--base');p.add_argument('--db');p.add_argument('--seeds');p.add_argument('--report',required=True);p.add_argument('--max-pages',type=int,default=12000);p.add_argument('--max-profiles',type=int,default=128)
    a=p.parse_args()
    if a.command=='crawl':
        out=crawl(a.cache,json.loads(Path(a.seeds).read_text()),a.max_pages,a.max_profiles)
        c=SourceCache(a.cache,'lxml')
        for *_,u in VOID_SOURCES:c.get(u)
    else:out=rebuild(a.base,a.db,a.cache)
    Path(a.report).write_text(json.dumps(out,ensure_ascii=False,indent=2));print(json.dumps(out,ensure_ascii=False),flush=True)
