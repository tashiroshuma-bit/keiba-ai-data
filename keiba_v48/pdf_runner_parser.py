"""Conservative extraction from JRA Yushun PDF first-page text.
Unrecognized lines are rejected, never silently inserted.
"""
import re
CIRCLED={**{chr(0x2460+i):i+1 for i in range(20)}}

def number(token):
    if token in CIRCLED:return CIRCLED[token]
    if token.isdigit():return int(token)
    raise ValueError('unknown horse number '+token)

def parse_runner_lines(text):
    rows=[];errors=[]
    for line in text.splitlines():
        m=re.match(r'^\s*(\d{1,2})\s+([①-⑳]|\d{1,2})\s+(.+?)\s+([牡牝セ#][０-９0-9]+)\s+(\d+(?:\.\d+)?)\s+(\S+)\s+(.+)$',line)
        if not m:continue
        rank,horse,name,sexage,weight,jockey,tail=m.groups()
        odds=re.findall(r'(?<!\d)(\d+\.\d+)[①-⑳]',tail)
        if len(odds)!=1:
            errors.append({'line':line,'reason':'ambiguous odds'});continue
        rows.append(dict(finish_position=int(rank),horse_number=number(horse),horse_name=name,
                         sex_age=sexage,carried_weight=float(weight),jockey=jockey,final_win_odds=float(odds[0])))
    return rows,errors

def validate(rows,expected_count=None):
    nums=[r['horse_number'] for r in rows];ranks=[r['finish_position'] for r in rows]
    issues=[]
    if not rows:issues.append('no rows')
    if len(nums)!=len(set(nums)):issues.append('duplicate horse numbers')
    if len(ranks)!=len(set(ranks)):issues.append('duplicate finishing positions: check dead heats')
    if expected_count is not None and len(rows)!=expected_count:issues.append('runner count mismatch')
    if rows and min(ranks)<1:issues.append('invalid rank')
    return issues
