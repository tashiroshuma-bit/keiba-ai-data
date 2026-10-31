"""Render all races, combined best five, day best five, and complete race sheets."""
import argparse,itertools,json
from pathlib import Path
from preoff_body_weight import markdown as body_weight_markdown

def pct(value):return f'{100*value:.2f}%'
def label(key):return str(key).removeprefix('馬番未定:')
def race_key(r):return r['date']+'_'+r['race']
def rank(r):return (-r['models']['A']['horses'][0]['p1'],r['date'],r['track'],r['race_number'])
def detail_path(r):return 'rider_details_20261031/'+race_key(r)+'.md'
def winner(r,letter):return r['models'][letter]['horses'][0]
def win_quote(r,horse):
    if r['quotes']['status']!='middle':return None
    return float(r['quotes']['odds']['1'][str(horse['number']).zfill(2)][0])

def race_report(r,relative_root='../'):
    q=r['quotes'];published=r['number_published']
    lines=[f"# {r['date']} {r['race']} 騎手反映後",'',
       f"平地・{len(r['runners'])}頭／発走{r['off_at']}。研究推定・未校正。2着・3着と馬券確率はPlackett–Luce近似。",
       f"[全レース一覧]({relative_root}RIDER_WEEKEND_OVERVIEW_20261031.md) ／ [JRA出馬表]({r['source']}) ／ [netkeiba出馬表]({r['independent_card_source']})",'',
       f"出馬表観測：{r['source_asof']}。外部指数は前回固定値を再利用。現在オッズは推定確率を学習・補正する入力に使用していません。",
       f"オッズ区分：{'現在オッズ' if q['status']=='middle' else '予想オッズのみ・現在オッズ未提供'}。取得：{q.get('observed_at','未取得')}。サイト更新：{q.get('official_datetime','記載なし')}（日本時間）。",
       '馬番未発表のレースは馬名で示し、掲載順を馬番へ変換しません。' if not published else '馬番は公式出馬表と照合済み。',
       '単勝40%／馬連25%／3連複30%に初めて達する最小点数。ワイド上位3点は参考表示。予想の的中率は事後実績ではありません。',
       '予算上限1万円・100円単位。配分は未実施、実購入なし。馬場適性・3着穴・収益確実性の追加判定は未算出。','',
       '|馬番|馬名|騎手|騎手実績件数|騎手特徴量|現在単勝|','|---|---|---|---:|---:|---:|']
    for h in r['runners']:
        quote=win_quote(r,h)
        lines.append(f"|{h['number'] if h['number'] is not None else '未発表'}|{h['name']}|{h['jockey']}|{h['jockey_history_samples']}|{h['jockey_form']:.4f}|{str(quote)+'倍' if quote else '未提供'}|")
    unlinked=sorted({h['jockey'] for h in r['runners'] if not h['jockey_id']})
    if unlinked:lines+=['','騎手履歴未連携：'+'、'.join(unlinked)+'。名前を確認したうえで、個別実績を推測せず事前値0.25を使用。']
    if r['excluded']:lines+=['','取消・除外：'+'、'.join(h['name'] for h in r['excluded'])+'。予測分母から除外。']
    repairs=[h for h in r['runners'] if h.get('jockey_parser_repair')]
    if repairs:lines+=['','騎手名の取り込み修復：'+' ／ '.join(h['name']+'：'+str(h['jockey_parser_repair']['old'])+' → '+h['jockey'] for h in repairs)]
    for letter in 'ABCD':
        m=r['models'][letter];weights={'A':'内部100%','B':'内部75%／外部25%','C':'内部50%／外部50%','D':'内部25%／外部75%'}
        lines+=['',f'## モデル{letter}（{weights[letter]}）','', '予想印：'+' ／ '.join(k+label(v) for k,v in m['marks'].items()),'',
           '|馬番・馬名|1着|2着|3着|3着以内|単勝EV参考倍率|','|---|---:|---:|---:|---:|---:|']
        for h in m['horses']:
            source=next(x for x in r['runners'] if x['name']==h['name']);quote=win_quote(r,source)
            ev=f"{h['p1']*quote:.3f}" if quote else '未算出'
            name=(str(h['number'])+' '+h['name']) if published else h['name']
            lines.append(f"|{name}|{pct(h['p1'])}|{pct(h['p2'])}|{pct(h['p3'])}|{pct(h['p1']+h['p2']+h['p3'])}|{ev}|")
        lines+=['','EV参考倍率＝未校正の1着推定×取得済み現在単勝オッズ。1.0が計算上の収支ゼロで、購入推奨・収益保証ではありません。']
        for kind,title in [('single','単勝'),('quinella','馬連'),('trio','3連複')]:
            t=m['priority'][kind]
            lines+=['',f"### {title}：{t['count']}点／合計{pct(t['cumulative'])}",'','|買い目|個別確率|合計確率|','|---|---:|---:|']
            for ticket in t['tickets']:lines.append('|'+ '－'.join(label(n) for n in ticket['numbers'])+'|'+pct(ticket['p'])+'|'+pct(ticket['cumulative'])+'|')
        probabilities={h['number']:h['p1'] for h in m['horses']}
        joint={}
        for i,j,k in itertools.permutations(probabilities,3):
            a,b,c=[probabilities[n] for n in (i,j,k)];joint[i,j,k]=a*b/(1-a)*c/(1-a-b)
        wide={pair:sum(v for triple,v in joint.items() if set(pair)<=set(triple)) for pair in itertools.combinations(sorted(probabilities),2)}
        selected=sorted(wide,key=lambda pair:(-wide[pair],pair))[:3]
        lines+=['','### ワイド上位3点（参考）','','|買い目|個別確率|重複除外後の合計|','|---|---:|---:|']
        for size,pair in enumerate(selected,1):
            union=sum(v for triple,v in joint.items() if any(set(p)<=set(triple) for p in selected[:size]))
            lines.append('|'+ '－'.join(label(n) for n in pair)+'|'+pct(wide[pair])+'|'+pct(union)+'|')
    return '\n'.join(lines[:2])+'\n'+body_weight_markdown(r)+'\n'+'\n'.join(lines[2:])+'\n'

def render(data):
    if data['race_failures'] or len(data['races'])!=46:raise ValueError('complete 46 flat races required')
    races=data['races'];best=sorted(races,key=rank)[:5];joined=sum(bool(h['jockey_id']) for r in races for h in r['runners'])
    repairs=sum(bool(h.get('jockey_parser_repair')) for r in races for h in r['runners'])
    lines=['# 10/31・11/1 平地全46レース 騎手反映後の再計算','',
       f"全46レース・{sum(len(r['runners']) for r in races)}頭を出馬表2サイトと照合。取消3頭・障害戦2レースを除外。騎手個別実績反映{joined}頭、履歴未連携31頭（C.デムーロ17、A.プーシャン11、渡辺竜也3）は事前値0.25。騎手名の旧取り込み誤り{repairs}行を修復。",
       f"学習済み重みは変更せず、騎手特徴量のみ実績へ接続。過去履歴{data['history_rows']:,}件、最新レース日{data['history_latest_race']}。馬の通算成績による簡易値・他特徴の平均補完は残り、正式な観測履歴モデルへの昇格はしていません。",
       '以下の「的中率」は未校正のモデル内推定確率です。レース前なので実際の的中率・収支は未確定。確率上昇は精度向上の実証ではありません。',
       'A＝内部100%、B＝内部75%／外部25%、C＝50%／50%、D＝内部25%／外部75%。外部指数は前回固定データを再利用。',
       '現在オッズ：10/31全23レース＋11/1天皇賞（秋）の計24レース。11/1の残り22レースは予想オッズのみのため現在オッズ・EVは未提供扱い。取得は日本時間10/31 03:23～03:32、各レースに取得・更新時刻を記載。',
       '単勝40%／馬連25%／3連複30%に達する最小点数、全頭1・2・3着・3着以内、ワイド上位3点と重複を除く合計を各レース詳細に掲載。現在オッズがある場合のみ単勝EV参考倍率を併記。予算上限1万円・100円単位、配分未実施・実購入なし。',
       '選定基準：モデルAの本命1着推定確率順。同率は日付・開催場・レース番号で固定。過去実測の的中率による選別ではありません。',
       '未確定のため目標的中率までの不足的中件数、実測90%以上の購入優先条件、収益確実性は未算出。','',
       '## 全レースの本命1着推定確率の平均','', '|対象|A|B|C|D|','|---|---:|---:|---:|---:|']
    for date in ('2026-10-31','2026-11-01','2日間全体'):
        subset=[r for r in races if date=='2日間全体' or r['date']==date]
        lines.append('|'+date+'|'+ '|'.join(pct(sum(winner(r,l)['p1'] for r in subset)/len(subset)) for l in 'ABCD')+'|')
    lines+=['','これは本命推定確率の算術平均で、事後実績の的中率ではありません。','','## 2日間を通したベスト5','','|順位|日付・レース|A本命|A 1着|現在単勝|詳細|','|---:|---|---|---:|---:|---|']
    for i,r in enumerate(best,1):
        h=winner(r,'A');source=next(x for x in r['runners'] if x['name']==h['name']);quote=win_quote(r,source)
        lines.append(f"|{i}|{r['date']} {r['race']}|{h['name']}|{pct(h['p1'])}|{str(quote)+'倍' if quote else '未提供'}|[全頭・買い目]({detail_path(r)})|")
    lines+=['','[ベスト5の全4モデル・全買い目をまとめて読む](BEST5_RIDER_RECALC_20261031.md)']
    for date in ('2026-10-31','2026-11-01'):
        subset=sorted((r for r in races if r['date']==date),key=lambda r:(r['track'],r['race_number']))
        lines+=['',f'## {date} 全23レース','','各セルはモデルごとの本命名と1着推定確率。馬番未発表は馬名のみ。','','|レース|A|B|C|D|全頭・買い目|','|---|---|---|---|---|---|']
        for r in subset:
            cells=[winner(r,l)['name']+' '+pct(winner(r,l)['p1']) for l in 'ABCD']
            lines.append('|'+r['race']+'|'+'|'.join(cells)+f'|[詳細]({detail_path(r)})|')
        lines+=['',f'### {date} ベスト5','','|順位|レース|A本命|1着推定|単勝40%最小点数|馬連25%|3連複30%|','|---:|---|---|---:|---:|---:|---:|']
        for i,r in enumerate(sorted(subset,key=rank)[:5],1):
            m=r['models']['A'];t=m['priority'];lines.append(f"|{i}|[{r['race']}]({detail_path(r)})|{m['horses'][0]['name']}|{pct(m['horses'][0]['p1'])}|{t['single']['count']}|{t['quinella']['count']}|{t['trio']['count']}|")
    lines+=['','## 主要レースの追加表示','']
    for date,track in [('2026-10-31','京都'),('2026-11-01','東京')]:
        r=next(r for r in races if r['date']==date and r['track']==track and r['race_number']==11)
        title='天皇賞（秋）' if date=='2026-11-01' else '京都11R'
        lines.append(f"- [{date} {title}：全頭・A〜D・全買い目]({detail_path(r)})")
    artifacts={'RIDER_WEEKEND_OVERVIEW_20261031.md':'\n'.join(lines)+'\n'}
    for r in races:artifacts[detail_path(r)]=race_report(r)
    artifacts['BEST5_RIDER_RECALC_20261031.md']='# 2日間ベスト5：全頭・4モデル・買い目\n\nモデルA本命1着推定確率順。未校正・事後実績ではありません。\n\n'+'\n\n---\n\n'.join(race_report(r,relative_root='') for r in best)
    return artifacts

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--prediction',required=True);p.add_argument('--directory',required=True);a=p.parse_args()
    artifacts=render(json.loads(Path(a.prediction).read_text()));folder=Path(a.directory)
    if any((folder/key).exists() for key in artifacts):raise ValueError('immutable output exists')
    for key,text in artifacts.items():
        dest=folder/key;dest.parent.mkdir(exist_ok=True,parents=True);dest.write_text(text)
    print(json.dumps({'reports':len(artifacts),'bytes':sum(len(text.encode()) for text in artifacts.values())}))
