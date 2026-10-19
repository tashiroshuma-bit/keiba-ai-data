"""Recover past-race time quality and explicitly supported exceptional fields.

Keep original PDF extraction status unchanged. An evidence overlay is admitted
only when field size, odds, times and exception semantics are all supported.
Dead heats and unknown statuses remain excluded.
"""
import math
import re

EXCEPTION='exceptional result requires separate rank/cancellation handling'


def parse_times(rows,expected,issues,raw_text,allow_exception=False):
    if expected<3 or len({r['horse_number'] for r in rows})!=len(rows):raise ValueError('incomplete PDF field')
    allowed=[EXCEPTION]
    if issues and not allow_exception:raise ValueError('unsupported PDF extraction issue')
    for issue in issues:
        if issue not in allowed and not issue.startswith(('runner count mismatch:','missing/invalid final odds: horse ')):
            raise ValueError('unsupported PDF extraction issue')
    if re.search(r'同着|失格|競走取りやめ',raw_text):raise ValueError('unsupported exceptional result')
    compact=re.sub(r'\s+','',raw_text)
    sections=[]
    for i,r in enumerate(rows):
        name=re.sub(r'\s+','',r.get('horse_name',''))
        start=compact.find(name) if name else -1
        next_name=re.sub(r'\s+','',rows[i+1].get('horse_name','')) if i+1<len(rows) else None
        end=compact.find(next_name,start+len(name)) if next_name and start>=0 else compact.find('単勝:',max(0,start))
        sections.append(compact[start:end] if start>=0 and end>start else '')
    output=[];previous=None;nonfinisher_started=False
    for index,raw in enumerate(rows):
        r=dict(raw);t=re.sub(r'\s+','',r.get('finish_time_raw',''));m=re.match(r'^(\d+):([0-5]\d)\.(\d)',t)
        short=re.match(r'^([0-5]?\d)\.(\d)',t)
        if m:seconds=int(m[1])*60+int(m[2])+int(m[3])/10;status='finished'
        elif short:seconds=int(short[1])+int(short[2])/10;status='finished'
        elif t.startswith('〃') and previous is not None:seconds=previous;status='finished'
        elif t.startswith('(競走') and '競走除外' in sections[index]:
            r.update(finish_time_seconds=None,runner_status='nonstarter',finish_position=None)
            output.append(r);continue
        elif '中止' in t or (t.startswith('(競走') and '競走中止' in sections[index]):seconds=None;status='nonfinisher';nonfinisher_started=True
        elif t.startswith('(出走') and any(x in sections[index] for x in ('出走取消','出走除外')):
            r.update(finish_time_seconds=None,runner_status='nonstarter',finish_position=None)
            output.append(r);continue
        else:raise ValueError('unknown or unparsed finish time')
        odds=r.get('final_win_odds')
        if odds is None or not math.isfinite(float(odds)) or float(odds)<1:raise ValueError('missing complete final odds')
        if seconds is not None:
            if nonfinisher_started or seconds<=0 or (previous is not None and seconds<previous-1e-9):raise ValueError('inconsistent time ordering')
            previous=seconds
        r.update(finish_time_seconds=seconds,runner_status=status,finish_position=sum(x['runner_status']=='finished' for x in output)+1 if status=='finished' else None)
        output.append(r)
    active=[r for r in output if r['runner_status']!='nonstarter']
    if len(active)!=expected:raise ValueError('incomplete PDF field')
    times=[r['finish_time_seconds'] for r in output if r['finish_time_seconds'] is not None]
    if len(times)<3:raise ValueError('insufficient verified finishers')
    mean=sum(times)/len(times);sd=math.sqrt(sum((t-mean)**2 for t in times)/len(times))
    for r in output:
        t=r['finish_time_seconds'];r.update(margin_seconds=t-min(times) if t is not None else None,relative_speed_z=(mean-t)/sd if t is not None and sd else None,field_size=len(active))
    return output


def fourth_corner(raw_text,active_numbers):
    """Full-field corner groups; tied clusters receive an explicit midrank."""
    import unicodedata
    text=unicodedata.normalize('NFKC',raw_text)
    section=re.search(r'通過順位(.*?)(?:勝\s*馬\s*の)',text,re.S)
    if not section:return None
    targets={int(n) for n in active_numbers};results=[]
    for marker in re.finditer(r'(?<![\d,(])4\s+',section[1]):
        seq=re.sub(r'\s+','',section[1][marker.end():]).replace('()',' )(').replace(' ','')
        if re.search(r'[^\d(),*\-=－ー]',seq):continue
        # Adjacent parenthesis glyphs can overlap in the PDF extraction. This
        # correction only exchanges an empty group boundary, never horses.
        pieces=re.findall(r'\([^()]+\)|\d+|[-=－ー,*]+',seq)
        if ''.join(pieces)!=seq:continue
        groups=[]
        for token in pieces:
            if token[0]=='(':
                if not re.fullmatch(r'\(\*?\d+(?:,\*?\d+)*\)',token):break
                groups.append(list(map(int,re.findall(r'\d+',token))))
            elif token.isdigit():groups.append([int(token)])
        else:
            numbers=[n for g in groups for n in g]
            if len(numbers)!=len(set(numbers)) or set(numbers)!=targets:continue
            positions={};at=1
            for group in groups:
                low,high=at,at+len(group)-1
                for n in group:positions[n]=dict(corner4_position=(low+high)/2,corner4_range=[low,high],corner4_method='printed_group_midrank_no_intragroup_order_claim')
                at=high+1
            results.append(positions)
    return results[0] if len(results)==1 else None
