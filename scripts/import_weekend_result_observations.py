"""Parse retrieved public result text; persist facts, not entire third-party pages.

Input: YYYYMMDD_TRACK_{result,yahoo}.txt exported from browser search text.
Each page hash identifies that text export, NOT original HTTP bytes.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LABELS = {'単勝': ('single', 1), '馬連': ('quinella', 2),
          'ワイド': ('wide', 2), '3連複': ('trio', 3), '3連単': ('trifecta', 3)}


def sections(text, yahoo=False):
    pattern = r'^## (\d+)R .*$' if yahoo else r'^(\d+)R (?!【).*$'
    matches = list(re.finditer(pattern, text, re.M))
    return {int(m[1]): text[m.end():matches[i+1].start() if i+1 < len(matches) else len(text)]
            for i, m in enumerate(matches)
            if re.search(r'^[123]\s+\|\s*\d+\s*\|\s*\d+\s*\|', text[m.end():matches[i+1].start() if i+1 < len(matches) else len(text)], re.M)}


def top3(text):
    return [[int(m[1]), int(m[2])] for m in re.finditer(r'^([123])\s+\|\s*\d+\s*\|\s*(\d+)\s*\|', text, re.M)]


def payouts(text, yahoo=False):
    out = {v[0]: {} for v in LABELS.values()}
    if yahoo:
        active = None
        for line in text.splitlines():
            cells = [c.strip() for c in line.split('|')]
            if cells[0] in LABELS:
                active = LABELS[cells.pop(0)][0]
            elif cells[0] in ('複勝', '枠連', '馬単'):
                active = None
            if active and len(cells) >= 2 and re.fullmatch(r'\d+(?:-\d+)*', cells[0]) and re.fullmatch(r'[\d,]+円', cells[1]):
                out[active][cells[0]] = int(cells[1][:-1].replace(',', ''))
        return out
    for label, (key, width) in LABELS.items():
        m = re.search(r'^'+label+r'\s*\|(.*?)(?=^(?:単勝|複勝|枠連|馬連|ワイド|馬単|3連複|3連単)\s*\||^△|\Z)', text, re.M | re.S)
        if not m:
            raise ValueError('missing payout '+label)
        cells = m[1].split('|')
        nums = list(map(int, re.findall(r'\d+', cells[0])))
        values = [int(x.replace(',', '')) for x in re.findall(r'([\d,]+)円', cells[1])]
        if len(nums) != width * len(values):
            raise ValueError((label, nums, values))
        out[key] = {'-'.join(map(str, nums[i*width:(i+1)*width])): value for i, value in enumerate(values)}
    return out


def main(folder):
    facts = []
    for date in ('20261024', '20261025'):
        for track, code in [('東京','05'), ('京都','08'), ('新潟','04')]:
            np = folder / f'{date}_{track}_result.txt'
            yp = folder / f'{date}_{track}_yahoo.txt'
            ns, ys = sections(np.read_text()), sections(yp.read_text(), True)
            day = ('08' if date.endswith('24') else '09') if code != '04' else ('03' if date.endswith('24') else '04')
            url = f'https://race.netkeiba.com/top/payback_list.html?kaisai_date={date}&kaisai_id=2026{code}04{day}'
            yurl = f'https://sports.yahoo.co.jp/keiba/race/list/26{code}04{day}'
            for race, section in ns.items():
                top, pay = top3(section), payouts(section)
                if race not in ys or top != top3(ys[race]) or pay != payouts(ys[race], True):
                    raise ValueError(('source disagreement', date, track, race, pay, payouts(ys.get(race,''), True)))
                scratches = list(map(int, re.findall(r'※ (\d+)番.*?返還', ys[race])))
                facts.append(dict(date=date, race=f'{track}{race}R', top3=top, payouts=pay, nonstarters=scratches,
                                  status='TWO_SECONDARY_SOURCES_AGREE_OFFICIAL_PENDING',
                                  sources=[url,yurl], source_text_export_sha256=[hashlib.sha256(p.read_bytes()).hexdigest() for p in (np,yp)]))
    # Desktop listing still showed速報; mobile page exposed the completed result.
    facts.append(dict(date='20261025', race='京都12R', top3=[[1,5],[2,12],[3,7]],
        payouts={'single':{'5':620},'quinella':{'5-12':880},'wide':{'5-12':390,'5-7':2790,'7-12':1850},
                 'trio':{'5-7-12':11670},'trifecta':{'5-12-7':61450}}, nonstarters=[],
        status='ONE_SECONDARY_SOURCE_OFFICIAL_PENDING',
        sources=['https://race.sp.netkeiba.com/?pid=race_result&race_id=202608040912&rf=rs'],
        source_text_export_sha256=[], note='Public completed result; not the desktop estimated-payout table.'))
    assert len(facts) == 72 and len({(r['date'],r['race']) for r in facts}) == 72
    target = ROOT / 'operations/results/2026-10-25/weekend_observations.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({'schema':'weekend-results-v1','observation_date':'2026-10-25',
        'official_verified':False,'races':facts}, ensure_ascii=False, indent=2)+'\n')
    print('Saved 72 races; 71 cross-checked on top-three and five payout markets; official pending.')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('text_export_folder', type=Path)
    main(p.parse_args().text_export_folder)
