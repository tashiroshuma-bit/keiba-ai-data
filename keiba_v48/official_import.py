"""Parse archived JRA official race results; output labels, NEVER pre-race odds."""
import argparse,csv,re
from bs4 import BeautifulSoup

def parse(html):
    soup=BeautifulSoup(html,'html.parser')
    for table in soup.find_all('table'):
        heads=' '.join(th.get_text(' ',strip=True) for th in table.find_all('th'))
        if not all(k in heads for k in ('馬名','騎手','着順','馬体重')): continue
        rows=[]
        for tr in table.find_all('tr'):
            cells=tr.find_all('td',recursive=False)
            vals=[c.get_text(' ',strip=True) for c in cells]
            if len(vals)<14 or not re.fullmatch(r'\d+',vals[0]):continue
            m=re.search(r'(\d{3})\s*\(\s*([+−-]?\d+)\s*\)',vals[11].replace('±','+'))
            rows.append(dict(finish_position=vals[0],gate=vals[1],horse_number=vals[2],horse_name=vals[3],sex_age=vals[4],carried_weight=vals[5],jockey=vals[6],finish_time=vals[7],corner_positions=vals[9],last_3f=vals[10],body_weight=m.group(1) if m else '',body_weight_change=m.group(2).replace('−','-') if m else '',trainer=vals[12],popularity=vals[13]))
        if rows:return rows
    raise ValueError('Official result table not parsed; inspect HTML structure')

def main():
    p=argparse.ArgumentParser();p.add_argument('html');p.add_argument('--race-id',required=True);p.add_argument('--race-date',required=True);p.add_argument('--source-url',required=True);p.add_argument('--out',default='results.csv');a=p.parse_args()
    rows=parse(open(a.html,encoding='utf-8').read())
    for r in rows:r.update(race_id=a.race_id,race_date=a.race_date,source_url=a.source_url,odds_at_cutoff='',odds_timestamp='',eligible_for_ev='no',data_role='POST_RACE_LABEL_ONLY')
    with open(a.out,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    print(f'Parsed {len(rows)} finishers; result labels only.')
if __name__=='__main__':main()
