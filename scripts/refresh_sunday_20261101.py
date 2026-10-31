"""Refresh published numbers/quotes/references without refitting on yesterday."""
import copy
import datetime as dt
import hashlib
import itertools
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.request import Request, urlopen
from bs4 import BeautifulSoup
from preoff_body_weight import attach, markdown, normalized, records_from_card, timestamp
from recalculate_weekend_riders import decode_odds

ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'reports/weekend_20261031_1101/ALL_FLAT_RIDER_RECALC_20261031T033252.json'
OLD_CARDS=ROOT/'reports/weekend_20261031_1101/ALL_FLAT_CARD_ODDS_20261030T183252Z.json'
OUT=ROOT/'reports/update_20261101'
JST=dt.timezone(dt.timedelta(hours=9))

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def fetch(url):
    with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=20) as response:
        raw=response.read()
    return raw,dict(url=url,at=dt.datetime.now(dt.timezone.utc).isoformat(),sha256=hashlib.sha256(raw).hexdigest())

def card_export(raw,meta):
    soup=BeautifulSoup(raw,'html.parser')
    return dict(meta,title=soup.title.get_text(' ',strip=True),
        header=soup.get_text(' ',strip=True).split('馬番 チェック')[0],
        rows=[dict(text=tr.get_text(' ',strip=True),
            cells=[dict(text=c.get_text(' ',strip=True),**{'class':c.get('class',[])}) for c in tr.find_all(['td','th'],recursive=False)],
            links=[dict(text=a.get_text(' ',strip=True),href=urljoin(meta['url'],a['href'])) for a in tr.find_all('a',href=True)])
            for tr in soup.select('table.Shutuba_Table tr.HorseList')])

def observe(race):
    code='2026'+('05' if race['track']=='東京' else '08')+'0411'+str(race['race_number']).zfill(2)
    url='https://race.sp.netkeiba.com/race/shutuba.html?race_id='+code
    out=dict(date=race['date'],race=race['race'],code=code)
    try:
        # Reuse the first actual observation made during this update.
        cache=ROOT.parent/'current_card.html';meta=ROOT.parent/'current_card_meta.json'
        cached_meta=json.loads(meta.read_text()) if meta.exists() else None
        fresh_cache=(cached_meta and dt.timedelta(0)<=dt.datetime.now(dt.timezone.utc)-timestamp(cached_meta['at'])<=dt.timedelta(minutes=15))
        if code=='202605041101' and cache.exists() and fresh_cache:
            raw=cache.read_bytes();m=json.loads(meta.read_text())
            if hashlib.sha256(raw).hexdigest()!=m['sha256']:raise ValueError('cached observation hash mismatch')
        else:raw,m=fetch(url)
        out['netkeiba']=card_export(raw,m)
    except Exception as exc:out['netkeiba']=dict(url=url,error=str(exc))
    params=dict(pid='api_get_jra_odds',input='UTF-8',output='jsonp',race_id=code,type=1,action='init',sort='odds',compress=1,callback='odds_callback')
    url='https://race.sp.netkeiba.com/?'+urlencode(params)
    try:
        raw,m=fetch(url);out['odds']=dict(m,text=raw.decode('utf-8'))
    except Exception as exc:out['odds']=dict(url=url,error=str(exc))
    return out

def profile_links(row,kind):
    return [urlsplit(a['href']).path for a in row['links'] if '/'+kind+'/' in a['href']]

def horse_info(row):
    return [normalized(c['text']) for c in row['cells'] if 'Horse_Info' in c['class']]

def refresh(base,observation,old_card,now):
    """Name-set + printed-number joins; verify jockey identity continuity."""
    snap=observation['netkeiba']
    if snap.get('error'):raise ValueError(snap['error'])
    observed=timestamp(snap['at']);off=timestamp(base['off_at'])
    if observed>now or observed>=off or observed.astimezone(JST).date()!=off.astimezone(JST).date():
        raise ValueError('same-day preoff entry observation required')
    oldrows={}
    for row in old_card['rows']:
        links=[a for a in row['links'] if a['text'].endswith('のデータベース') and '/horse/' in a['href']]
        if len(links)==1:oldrows[normalized(links[0]['text'].removesuffix('のデータベース'))]=row
    byname={normalized(h['name']):h for h in base['runners']}
    parsed={};numbers=set()
    for row in snap['rows']:
        # Other page tables reuse HorseList for pace examples and templates.
        if not any('Weight' in c['class'] for c in row['cells']):continue
        links=[a for a in row['links'] if a['text'].endswith('のデータベース') and '/horse/' in a['href']]
        if len(links)!=1:raise ValueError('one current horse profile required')
        name=normalized(links[0]['text'].removesuffix('のデータベース'))
        if name not in byname or name in parsed:raise ValueError('runner set changed or duplicate')
        cells=[c for c in row['cells'] if any(re.fullmatch(r'Waku[1-8]',v) for v in c['class']) or 'Umaban' in c['class']]
        if len(cells)!=1 or not cells[0]['text'].isdigit():raise ValueError('published printed horse number required')
        number=int(cells[0]['text'])
        if number in numbers or not 1<=number<=18:raise ValueError('duplicate or invalid number')
        numbers.add(number)
        frames=[int(v[-1]) for c in row['cells'] for v in c['class'] if re.fullmatch(r'Waku[1-8]',v)]
        old=oldrows.get(name)
        old_jockey=profile_links(old,'jockey') if old else []
        new_jockey=profile_links(row,'jockey')
        # Previously unlinked visiting riders may gain a netkeiba link. Keep
        # their old unlinked prior; identical printed horse/rider/weight text
        # proves continuity but is not a new official identity/history join.
        added_unlinked=(not old_jockey and len(new_jockey)==1 and not byname[name].get('jockey_id')
                        and horse_info(old)==horse_info(row) and bool(horse_info(row))) if old else False
        if not old or profile_links(old,'horse')!=profile_links(row,'horse') or (old_jockey!=new_jockey and not added_unlinked):
            raise ValueError('horse/jockey profile changed; cannot reuse old features')
        if horse_info(old) and horse_info(old)!=horse_info(row):raise ValueError('printed rider/weight information changed')
        h=copy.deepcopy(byname[name])
        if h['number'] is not None and h['number']!=number:raise ValueError('previously confirmed number changed')
        h.update(number=number,display_key=number,frame=frames[0] if frames else None,
            withdrawn='取消' in row['text'] or '除外' in row['text'])
        h['netkeiba_horse_profile_url']=links[0]['href'];parsed[name]=h
        if added_unlinked:h['current_rider_link_note']='new netkeiba link only; printed information unchanged; prior identity/history remains unlinked'
    if set(parsed)!=set(byname):raise ValueError('current runner set mismatch')
    if any(h['withdrawn'] for h in parsed.values()):raise ValueError('new withdrawal requires probability recomputation, not a stale recommendation')
    out=copy.deepcopy(base);out['runners']=sorted(parsed.values(),key=lambda h:h['number'])
    out['number_published']=True
    for letter in 'ABCD':
        m=out['models'][letter]
        keymap={h['number']:parsed[normalized(h['name'])]['number'] for h in base['models'][letter]['horses']}
        for h in m['horses']:h['number']=parsed[normalized(h['name'])]['number']
        m['marks']={mark:keymap[key] for mark,key in m['marks'].items()}
        m['ordered_top3']=[keymap[key] for key in m['ordered_top3']]
        for bucket in m['priority'].values():
            for ticket in bucket['tickets']:ticket['numbers']=[keymap[key] for key in ticket['numbers']]
    out['quotes']=decode_odds(observation['odds'])
    if out['quotes']['status']=='middle':
        q=out['quotes']
        if timestamp(q['observed_at'])>=off or timestamp(q['observed_at'])>now:raise ValueError('late odds')
        if not all(str(h['number']).zfill(2) in q.get('odds',{}).get('1',{}) for h in out['runners']):raise ValueError('incomplete current odds')
    out['current_entry_observation']={k:snap[k] for k in ('url','at','sha256')}
    out['probability_update']='unchanged_by_name_no_refit_on_20261031'
    out['track_reference']='10/31 only; 11/1 actual going and race bias not observed'
    out=attach(out,records_from_card(snap,out['runners'],out['off_at']),now)
    return out

def markets(race,letter):
    rows=race['models'][letter]['horses'];p={h['number']:h['p1'] for h in rows};triples={};pairs={};trios={};wide={};exacta={}
    for i,j,k in itertools.permutations(sorted(p),3):
        value=p[i]*p[j]/(1-p[i])*p[k]/(1-p[i]-p[j]);triples[i,j,k]=value
        pair=tuple(sorted((i,j)));trio=tuple(sorted((i,j,k)))
        pairs[pair]=pairs.get(pair,0)+value;trios[trio]=trios.get(trio,0)+value
        exacta[i,j]=exacta.get((i,j),0)+value
        for pair in itertools.combinations(sorted((i,j,k)),2):wide[pair]=wide.get(pair,0)+value
    place={}
    for triple,value in triples.items():
        for n in triple[:3 if len(p)>=8 else 2]:place[n,]=place.get((n,),0)+value
    frame={h['number']:h['frame'] for h in race['runners']};bracket={}
    if all(frame.values()):
        for (i,j),v in pairs.items():
            key=tuple(sorted((frame[i],frame[j])));bracket[key]=bracket.get(key,0)+v
    return {'複勝':place,'ワイド':wide,'単勝':{(n,):v for n,v in p.items()},'枠連':bracket,'馬連':pairs,'3連複':trios,'馬単':exacta,'3連単':triples}

def ordered(values):return sorted(values.items(),key=lambda kv:(-kv[1],kv[0]))
def pct(value):return f'{100*value:.2f}%'
def ticket(numbers):return '－'.join(map(str,numbers))

def detail(race):
    names={h['number']:h['name'] for h in race['runners']};q=race['quotes'];snap=race['current_entry_observation']
    lines=[f"# 11/1 {race['race']} 更新予測",'',f"発走 {race['off_at']} ／ [一覧](README.md)",'',
        '**暫定版：馬体重の全頭確認前。確率は未校正の保存モデル推定です。**',
        '10/31の結果だけで係数・混合率を選び直さず、A〜Dの馬名別確率を維持。最新出馬表で馬番・騎手プロフィールの継続を確認。',
        '昨日の良馬場や脚質傾向を本日の確定状態と扱わない。本日の馬場・展開による数値補正は未実施。',
        '馬体重は前走比・同馬履歴・休養間隔と比較し、増減だけでは加減点しない。','',
        f"出馬表実観測 {snap['at']} ／ [出典]({snap['url']}) ／ SHA256 `{snap['sha256']}`",
        f"オッズ区分 {q['status']} ／ 取得 {q.get('observed_at','未取得')} ／ サイト更新 {q.get('official_datetime','記載なし')}",
        '外部指数・騎手履歴は前回固定値。現在オッズを勝率の入力には使用しません。', '',markdown(race),
        '## 買い方の比較','',
        '各券種の全候補から、1点の的中推定が最大のものを比較。複勝は8頭以上で3着以内、5〜7頭で2着以内。',
        '**馬体重・複勝等の現在配当と条件確認前の購入配分は0円。** 予算上限は1レース1万円。的中確率と利益確率は別です。', '',
        '|モデル|1点の最高候補|馬名|的中推定|','|---|---|---|---:|']
    allmarkets={letter:markets(race,letter) for letter in 'ABCD'}
    for letter,values in allmarkets.items():
        best=max(((v,kind,n) for kind,bucket in values.items() for n,v in bucket.items()),key=lambda x:x[0]);v,kind,n=best
        lines.append(f"|{letter}|{kind} {ticket(n)}|{'・'.join(names[i] for i in n) if kind!='枠連' else '枠番'}|{pct(v)}|")
    for letter in 'ABCD':
        lines+=['',f'## モデル{letter}','','|馬番・馬名|1着|2着|3着|3着以内|現在単勝|','|---|---:|---:|---:|---:|---:|']
        for h in race['models'][letter]['horses']:
            n=h['number'];quote=q.get('odds',{}).get('1',{}).get(str(n).zfill(2)) if q['status']=='middle' else None
            lines.append(f"|{n} {h['name']}|{pct(h['p1'])}|{pct(h['p2'])}|{pct(h['p3'])}|{pct(h['p1']+h['p2']+h['p3'])}|{quote[0]+'倍' if quote else '未確認'}|")
        lines+=['','### 8券種の最上位1点','','|券種|候補|推定|','|---|---|---:|']
        for kind,bucket in allmarkets[letter].items():
            if bucket:
                n,v=ordered(bucket)[0];lines.append(f'|{kind}|{ticket(n)}|{pct(v)}|')
        for kind in ('単勝','馬連','ワイド','3連複'):
            ranked=ordered(allmarkets[letter][kind]);lines+=['',f'### {kind} 全{len(ranked)}通り','','|順位|組み合わせ|個別推定|','|---:|---|---:|']
            for i,(n,v) in enumerate(ranked,1):
                if i==11:lines+=['','<details><summary>11位以下をすべて表示</summary>','','|順位|組み合わせ|個別推定|','|---:|---|---:|']
                lines.append(f'|{i}|{ticket(n)}|{pct(v)}|')
            if len(ranked)>10:lines+=['','</details>']
    return '\n'.join(lines)+'\n'

def run(out_directory=OUT):
    OUT=Path(out_directory)
    OUT.mkdir(parents=True,exist_ok=True);evidence_path=OUT/'ENTRY_ODDS_OBSERVATIONS.json';prediction_path=OUT/'PREDICTIONS.json'
    if prediction_path.exists():raise ValueError('immutable revision already exists')
    old=json.loads(OLD.read_text());races=[r for r in old['races'] if r['date']=='2026-11-01'];assert len(races)==23
    if evidence_path.exists():evidence=json.loads(evidence_path.read_text())
    else:
        with ThreadPoolExecutor(max_workers=3) as ex:observations=list(ex.map(observe,races))
        evidence=dict(schema='same-day-entry-odds-v1',races=observations)
        evidence_path.write_text(json.dumps(evidence,ensure_ascii=False,separators=(',',':'))+'\n')
    oldcards={(r['date'],r['race']):r['netkeiba'] for r in json.loads(OLD_CARDS.read_text())['races']}
    obs={r['race']:r for r in evidence['races']};updated=[];failures=[];now=dt.datetime.now(dt.timezone.utc)
    for race in races:
        try:updated.append(refresh(race,obs[race['race']],oldcards[race['date'],race['race']],now))
        except Exception as exc:failures.append(dict(race=race['race'],error=str(exc)))
    data=dict(schema='sunday-observation-refresh-v1',created_at=now.isoformat(),date='2026-11-01',
        parent_prediction_sha256=digest(OLD),entry_odds_sha256=digest(evidence_path),races=updated,race_failures=failures,
        model_version='v49',model_weights_changed=False,probabilities_changed_by_name=False,actual_bets=False,
        result_reference='reports/review_20261031/FOUR_MODEL_SETTLEMENT_20261031T192204+0900.md')
    prediction_path.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'))+'\n')
    best=sorted(updated,key=lambda r:(-r['models']['A']['horses'][0]['p1'],r['track'],r['race_number']))[:5]
    selected=best+[r for r in updated if r['race']=='東京11R' and r not in best]
    lines=['# 11/1 更新予測｜ベスト5＋天皇賞（秋）','',
        '10/31の結果を踏まえた当日確認版。23平地レースを対象、京都4R障害は対象外。',
        '昨日1日の成績で混合率・係数を変更しない。未校正の高い数値を実測的中率と扱わず、馬体重未確認は暫定。',
        '馬番と騎手継続を当日出馬表で確認。馬名ごとの確率は保存値と同じ。馬体重・当日馬場による数値補正は未実施。',
        '全額を自動配分する表示をやめ、直前情報と配当確認前の配分は0円。上限1R1万円・実購入なし。',
        'A=内部100%、B=内部75%＋外部25%、C=50%＋50%、D=内部25%＋外部75%。外部指数は前回固定値。', '',
        '[10/31公式照合](../review_20261031/FOUR_MODEL_SETTLEMENT_20261031T192204+0900.md) ／ [馬体重参照ルール](../../operations/PREOFF_BODY_WEIGHT_POLICY.md)', '',
        '## ベスト5＋重賞','', '選定は従来通りAの本命1着推定順。買い方の候補は全8券種の各1点を比較。', '',
        '|区分・詳細|発走|A本命・1着推定|的中推定最大の1点|推定|馬体重|','|---|---|---|---|---:|---|']
    for i,r in enumerate(selected):
        h=r['models']['A']['horses'][0];m=markets(r,'A');v,kind,n=max((v,k,n) for k,b in m.items() for n,v in b.items())
        lines.append(f"|[{i+1 if i<5 else '重賞'} {r['race']}]({r['race']}.md)|{timestamp(r['off_at']).astimezone(JST):%H:%M}|{h['number']} {h['name']} {pct(h['p1'])}|{kind} {ticket(n)}|{pct(v)}|{r['preoff_body_weight_review']['observed']}/{len(r['runners'])}頭|")
    lines+=['','## 全23平地レース','','|詳細|発走|A本命|1着推定|馬体重|','|---|---|---|---:|---|']
    for r in sorted(updated,key=lambda r:(r['track'],r['race_number'])):
        h=r['models']['A']['horses'][0]
        lines.append(f"|[{r['race']}]({r['race']}.md)|{timestamp(r['off_at']).astimezone(JST):%H:%M}|{h['number']} {h['name']}|{pct(h['p1'])}|{r['preoff_body_weight_review']['observed']}/{len(r['runners'])}頭|")
        (OUT/(r['race']+'.md')).write_text(detail(r))
    if failures:lines+=['','確認できず更新対象から隔離：'+json.dumps(failures,ensure_ascii=False)]
    lines+=['','[観測データ](ENTRY_ODDS_OBSERVATIONS.json) ／ [更新予測・親ハッシュ](PREDICTIONS.json)', '',
        f"実観測範囲：{min(o['netkeiba'].get('at',now.isoformat()) for o in evidence['races'])} ～ {max(o['netkeiba'].get('at',now.isoformat()) for o in evidence['races'])}（UTC）。本日の実馬場・レース傾向は未観測。"]
    (OUT/'README.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(dict(updated=len(updated),runners=sum(len(r['runners']) for r in updated),failures=failures),ensure_ascii=False))

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--output-directory',type=Path,default=OUT)
    run(parser.parse_args().output_directory)
