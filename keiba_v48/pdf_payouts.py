"""Decode annual-report winning payouts using the printed ordered trifecta.

Unknown CIDs are resolved only inside one race's payout block. The official
3-ren-tan winning sequence maps its three printed symbols to verified ranks
1/2/3. Independent win/exacta/trio/wide checks must all agree. This recovers
winning payouts, never missing final market quotes for losing combinations.
"""
import itertools
import re
import unicodedata

TOKEN=r'(?:\(cid:\d+\)|[①-⑳])'


def symbol_tokens(text):
    tokens=re.findall(TOKEN,text)
    if ''.join(tokens)!=re.sub(r'\s+','',text):raise ValueError('ambiguous payout symbols')
    return tokens


def decode_payouts(raw_text,finish_by_number,expected_win_payout=None):
    if sorted(finish_by_number.values())[:3]!=[1,2,3]:raise ValueError('unique verified top3 required')
    top=[str(next(n for n,rank in finish_by_number.items() if rank==i)) for i in (1,2,3)]
    if len({n for n,rank in finish_by_number.items() if rank in (1,2,3)})!=3:raise ValueError('unsupported tie')
    # Do not include sales totals or the subsequent ticket-count table.
    start=re.search(r'単\s*勝\s+('+TOKEN+r')\s+([\d,]+)円',raw_text)
    end=re.search(r'単勝票数',raw_text)
    if not start or not end or end.start()<=start.start():raise ValueError('payout block not isolated')
    block=raw_text[start.start():end.start()]
    tri=re.search(r'3\s*連\s*単\s*((?:'+TOKEN+r'){3})\s+([\d,]+)円',block)
    if not tri:raise ValueError('ordered trifecta anchor absent')
    tokens=symbol_tokens(tri[1])
    if len(tokens)!=3 or len(set(tokens))!=3:raise ValueError('ambiguous trifecta anchor')
    mapping=dict(zip(tokens,top))
    # Unicode circled numbers carry their own identity; CIDs do not.
    for token,number in mapping.items():
        if not token.startswith('(cid:') and str(ord(token)-0x2460+1)!=number:raise ValueError('anchor contradicts explicit horse number')
    win_number=mapping.get(start[1]);win=int(start[2].replace(',',''))
    if win_number!=top[0] or win<100 or (expected_win_payout is not None and win!=expected_win_payout):raise ValueError('single-win cross-check failed')
    exacta=re.search(r'馬\s*単\s*((?:'+TOKEN+r'){2})\s+([\d,]+)円',block)
    if not exacta or [mapping.get(t) for t in symbol_tokens(exacta[1])]!=top[:2]:raise ValueError('exacta cross-check failed')
    trio=re.search(r'3\s*連\s*複\s*((?:'+TOKEN+r'){3})\s+([\d,]+)円',block)
    if not trio or {mapping.get(t) for t in symbol_tokens(trio[1])}!=set(top):raise ValueError('trio cross-check failed')
    wide=re.search(r'ワ\s*イ\s*ド\s*(.*?)3\s*連\s*複',block,re.S)
    if not wide:raise ValueError('wide payout section absent')
    pairs=re.findall(r'((?:'+TOKEN+r'){2})\s+([\d,]+)円',wide[1])
    result={'win:'+top[0]:win,'trio:'+','.join(sorted(top,key=int)):int(trio[2].replace(',',''))}
    for printed,amount in pairs:
        ns=[mapping.get(t) for t in symbol_tokens(printed)]
        if None in ns or len(set(ns))!=2:raise ValueError('wide pair cross-check failed')
        key='wide:'+','.join(sorted(ns,key=int))
        if key in result:raise ValueError('duplicate wide payout')
        result[key]=int(amount.replace(',',''))
    expected={'wide:'+','.join(sorted(pair,key=int)) for pair in itertools.combinations(top,2)}
    if {k for k in result if k.startswith('wide:')}!=expected or any(v<100 for v in result.values()):raise ValueError('incomplete or invalid wide payouts')
    return result,dict(method='ordered_trifecta_anchor_with_win_exacta_trio_wide_cross_checks',symbol_to_horse_number=mapping)
