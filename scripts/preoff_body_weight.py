"""Same-day announced body mass as a reference; never substitute carried weight.

This module does not invent a learned body-mass coefficient or change p1/p2/p3.
The explicit final-reference gate prevents missing/late evidence being called final.
"""
import copy
import datetime as dt
import hashlib
import json
import math
import re
import unicodedata

JST=dt.timezone(dt.timedelta(hours=9))


def timestamp(value):
    at=dt.datetime.fromisoformat(value)
    if at.tzinfo is None:
        raise ValueError('timezone required')
    return at


def normalized(value):
    return re.sub(r'\s+','',unicodedata.normalize('NFKC',value))


def validate(record, horse, off_at, now):
    off=timestamp(off_at); at=timestamp(record['observed_at'])
    if record.get('basis')!='announced_preoff':
        raise ValueError('announced preoff body weight required, not result-page data')
    if (at>now or at>=off or at.astimezone(JST).date()!=off.astimezone(JST).date()):
        raise ValueError('same-day observation before off required')
    if (record.get('number')!=horse.get('number') or
            normalized(record.get('name',''))!=normalized(horse['name'])):
        raise ValueError('runner number and name mismatch')
    source=record.get('source_url','')
    if not source.startswith('https://') or any(x in source.lower() for x in ('race_result','result.html','/result/','accesss.html','payback')):
        raise ValueError('preoff entry source required')
    if record.get('hash_basis') not in ('http_bytes','observed_text_export'):
        raise ValueError('explicit hash basis required')
    if not re.fullmatch('[0-9a-f]{64}',record.get('source_sha256','')):
        raise ValueError('source hash required')
    body=record.get('body_weight_kg'); change=record.get('change_kg')
    if isinstance(body,bool) or not isinstance(body,(int,float)) or not math.isfinite(body) or not 250<=body<=700:
        raise ValueError('invalid body mass; carried weight is not body weight')
    debut=record.get('first_start',False)
    if change is None:
        if not debut:
            raise ValueError('change must be observed; unknown is not zero')
    elif (debut or isinstance(change,bool) or not isinstance(change,(int,float))
          or not math.isfinite(change) or abs(change)>150 or not 250<=body-change<=700):
        raise ValueError('invalid or conflicting previous-body-weight change')
    return dict(record)


def reference(record, horse, off_at):
    """Describe comparisons only; larger/smaller is not automatically good/bad."""
    body=record['body_weight_kg']; delta=record['change_kg']
    previous=body-delta if delta is not None else None
    history=[]
    for row in record.get('history',[]):
        if (not horse.get('horse_profile_url') or
                row.get('horse_profile_url')!=horse['horse_profile_url']):
            raise ValueError('historical body weight requires the same attested horse profile')
        if (not row.get('source_url','').startswith('https://') or
                not re.fullmatch('[0-9a-f]{64}',row.get('source_sha256',''))):
            raise ValueError('historical body weight requires source evidence')
        # Historical references must have actual observations before today's record.
        at=timestamp(row['observed_at'])
        if at>timestamp(record['observed_at']) or timestamp(row['off_at'])>=timestamp(off_at):
            raise ValueError('future history cannot enter body-weight reference')
        mass=row.get('body_weight_kg')
        if (not isinstance(mass,(int,float)) or isinstance(mass,bool)
                or not math.isfinite(mass) or not 250<=mass<=700):
            raise ValueError('invalid historical body mass')
        history.append(row)
    history=sorted(history,key=lambda r:timestamp(r['off_at']))[-3:]
    values=[r['body_weight_kg'] for r in history]
    last=horse.get('last_off_at')
    if last:
        if timestamp(last)>=timestamp(off_at):raise ValueError('future last race')
        rest_days=(timestamp(off_at)-timestamp(last)).days
    else:rest_days=None
    return dict(status='reference_only',body_weight_kg=body,change_kg=delta,
        previous_body_weight_kg=previous,change_pct=100*delta/previous if previous else None,
        first_start=record.get('first_start',False),history_samples=len(values),
        recent_range_kg=[min(values),max(values)] if values else None,
        outside_recent_range=(body<min(values) or body>max(values)) if values else None,
        rest_days=rest_days,observed_at=record['observed_at'],source_url=record['source_url'],
        source_sha256=record['source_sha256'],hash_basis=record['hash_basis'],
        probability_adjustment_applied=False,
        interpretation='Compare to this horse, age/growth, interval and condition; do not mechanically penalize gain/loss or reward zero change.')


def attach(race, records=(), now=None, require_final=False):
    now=now or dt.datetime.now(dt.timezone.utc)
    result=copy.deepcopy(race); candidates=list(records)
    numbers=[r['number'] for r in candidates]
    if len(numbers)!=len(set(numbers)):
        raise ValueError('duplicate body-weight runner')
    active=[h for h in result['runners'] if not h.get('withdrawn')]
    if set(numbers)-{h.get('number') for h in active}:
        raise ValueError('weight observations outside active field')
    mapped={r['number']:r for r in candidates}; count=0
    for h in active:
        record=mapped.get(h.get('number'))
        if record:
            h['body_weight_reference']=reference(validate(record,h,result['off_at'],now),h,result['off_at']); count+=1
        else:
            # Never reuse stale reference metadata from the input freeze.
            h['body_weight_reference']={'status':'not_observed','probability_adjustment_applied':False}
    complete=count==len(active) and count>0
    if require_final and (not complete or now>=timestamp(result['off_at'])):
        raise ValueError('final reference requires all active runners observed and forecast before off')
    result['preoff_body_weight_review']=dict(status='all_observed_reference_only' if complete else 'provisional_missing_body_weight',
        observed=count,active_runners=len(active),all_active_observed=complete,
        probability_adjustment_applied=False,learned_coefficient_available=False,
        final_reference_gate_passed=bool(require_final and complete),
        reviewed_at=now.isoformat())
    return result


def records_from_card(snapshot, horses, off_at):
    """Extract only the current Weight column of observed netkeiba entry rows."""
    if snapshot.get('error'):return []
    out=[]
    for row in snapshot.get('rows',[]):
        cells=row.get('cells',[])
        weight=[c['text'] for c in cells if any(cls.lower() in ('weight','horseweight') for cls in c.get('class',[]))]
        if not weight:continue
        links=[a for a in row.get('links',[]) if '/horse/' in a.get('href','') and a.get('text','').endswith('のデータベース')]
        if len(links)!=1:continue
        name=links[0]['text'].removesuffix('のデータベース')
        matches=[h for h in horses if normalized(h['name'])==normalized(name) and not h.get('withdrawn')]
        if len(matches)!=1:raise ValueError('body-weight row does not match one active horse')
        token=normalized(weight[0]); match=re.fullmatch(r'(\d{3})(?:kg)?\(([+\-]?\d+|初出走)\)',token)
        if not match:
            if not token or token in ('--','---','計不'):continue
            raise ValueError('unrecognized current body weight')
        # Require the number printed on that same entry row; never join name alone.
        numbers=[c['text'].strip() for c in cells if 'Umaban' in c.get('class',[])]
        if len(numbers)!=1 or not numbers[0].isdigit() or int(numbers[0])!=matches[0]['number']:
            raise ValueError('body-weight row number mismatch')
        debut=match[2]=='初出走' or matches[0].get('starts')==0
        out.append(dict(number=matches[0]['number'],name=name,body_weight_kg=int(match[1]),
            change_kg=None if debut else int(match[2]),first_start=debut,basis='announced_preoff',
            observed_at=snapshot['at'],source_url=snapshot['url'],source_sha256=snapshot['sha256'],hash_basis='http_bytes'))
    return out


def markdown(race):
    review=race.get('preoff_body_weight_review',{})
    lines=['## 直前馬体重の参考評価','',
        f"確認 {review.get('observed',0)}/{review.get('active_runners',len(race['runners']))}頭。"+
        ('全頭観測済み。' if review.get('all_active_observed') else '未確認を含む暫定版。'),
        '馬体重は参考評価へ反映。学習済みの確率補正係数はなく、確率は馬体重補正済みではありません。', '',
        '|馬番・馬名|馬体重|増減|前走比|過去3走の観測範囲|休養日数|', '|---|---:|---:|---:|---|---:|']
    for h in race['runners']:
        if h.get('withdrawn'):continue
        r=h.get('body_weight_reference',{})
        prefix=str(h.get('number') or '未発表')+' '+h['name']
        if r.get('status')!='reference_only':lines.append('|'+prefix+'|未確認|未確認|未確認|未確認|未確認|');continue
        delta='初出走' if r.get('first_start') else f"{r['change_kg']:+g}kg"
        change='対象外' if r['change_pct'] is None else f"{r['change_pct']:+.2f}%"
        bounds=r['recent_range_kg'];bounds='未確認' if bounds is None else f'{bounds[0]}〜{bounds[1]}kg（{r["history_samples"]}走）'
        lines.append(f"|{prefix}|{r['body_weight_kg']}kg|{delta}|{change}|{bounds}|{r['rest_days'] if r['rest_days'] is not None else '未確認'}|")
    return '\n'.join(lines)+'\n'
