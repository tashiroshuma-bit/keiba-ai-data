"""Render rider-overlay research results with observed public odds."""
import argparse,base64,itertools,json,zlib
from pathlib import Path

def render(prediction,evidence):
    quotes={}
    for row in evidence['odds']:
        text=row['text'];assert text.startswith('odds_callback(') and text.endswith(')')
        response=json.loads(text[len('odds_callback('):-1])
        if response['status']!='middle':raise ValueError('current odds required; predicted/final odds are different')
        data=json.loads(zlib.decompress(base64.b64decode(response['data'])))
        quotes[row['race']]={**data,'observed_at':row['at'],'source_url':row['url'],'source_sha256':row['sha256']}
    pct=lambda x:f'{100*x:.2f}%'
    lines=['# 騎手別実績の反映とnetkeiba現在オッズの照合','',
      '対象：ユーザー指定の2026年10月31日・平地5レース。全46レースの再計算完了を示すものではありません。',
      '内部モデルA＝100%、B＝75%／外部25%、C＝50%／50%、D＝25%／75%。',
      '既存の学習済み重みを保持し、騎手成績の入力を平均値から観測済み実績へ変更しました。馬の能力などの残りの入力には従来の通算成績による簡易値・平均値が残ります。',
      '以下は未校正の研究推定値です。数値の上昇は予測精度が向上した実証ではありません。2・3着と馬券確率は従来と同じPlackett–Luce近似です。',
      f"履歴{prediction['history_rows']:,}件、最新レース日{prediction['history_latest_race']}。騎手特徴量は有効着順の過去出走について（3着以内回数＋5）÷（出走数＋20）。中止・未出走はこの分母に入りません。",
      '単勝40%・馬連25%・3連複30%を超える最小点数。ワイドは上位3点の参考表示で、重複を除いた合計を使います。配分は未実施・実購入なし。',
      '', '|レース|A首位・騎手|反映前→後の1着推定|netkeiba単勝|サイト更新時刻（日本時間）|','|---|---|---:|---:|---|']
    for race in prediction['races']:
        q=quotes[race['race']];numbers={int(n) for n in q['odds']['1']}
        assert numbers=={h['number'] for h in race['runners']}
        best=race['models']['A']['horses'][0];horse=next(h for h in race['runners'] if h['number']==best['number']);old=next(h for h in race['old_A'] if h['number']==best['number'])
        lines.append(f"|{race['race']}|{best['number']} {best['name']}／{horse['jockey']}|{pct(old['p1'])} → {pct(best['p1'])}|{q['odds']['1'][str(best['number']).zfill(2)][0]}倍|{q['official_datetime']}|")
    for race in prediction['races']:
        q=quotes[race['race']]
        lines+=['',f"## {race['race']}",'',f"[JRA出馬表]({race['source']}) ／ [netkeiba出馬表](https://race.sp.netkeiba.com/race/shutuba.html?race_id="+next(r['code'] for r in evidence['races'] if r['race']==race['race'])+')',
          f"現在オッズの取得時刻：{q['observed_at']}（UTC）。サイト更新時刻：{q['official_datetime']}（日本時間）。予想オッズではなく応答区分middleの単勝・複勝を取得。",
          '', '|馬番|馬名|騎手|履歴件数|騎手特徴量|単勝|複勝|','|---:|---|---|---:|---:|---:|---:|']
        for h in race['runners']:
            key=str(h['number']).zfill(2);win=q['odds']['1'][key][0];place=q['odds']['2'][key]
            lines.append(f"|{h['number']}|{h['name']}|{h['jockey']}|{h['jockey_history_samples']}|{h['jockey_form']:.4f}|{win}|{place[0]}–{place[1]}|")
        missing=sorted({h['jockey'] for h in race['runners'] if not h['jockey_id']})
        if missing:lines+=['','既存DBの公式ID証拠と一致しなかった騎手：'+ '、'.join(missing)+'。個別履歴を推測で補わず、事前値0.25・ID未連携の扱いです。']
        for letter,m in race['models'].items():
            lines+=['',f'### モデル{letter}','', '予想印：'+' ／ '.join(k+str(v) for k,v in m['marks'].items()),'', '|馬番|馬名|1着|2着|3着|3着以内|','|---:|---|---:|---:|---:|---:|']
            for h in m['horses']:lines.append(f"|{h['number']}|{h['name']}|{pct(h['p1'])}|{pct(h['p2'])}|{pct(h['p3'])}|{pct(h['p1']+h['p2']+h['p3'])}|")
            lines+=['','<details><summary>買い目・個別確率・合計確率</summary>','']
            for kind,label in [('single','単勝'),('quinella','馬連'),('trio','3連複')]:
                ticket=m['priority'][kind];lines+=[f"{label}：{ticket['count']}点、合計{pct(ticket['cumulative'])}",'','|買い目|個別確率|合計確率|','|---|---:|---:|']
                for t in ticket['tickets']:lines.append('|'+ '–'.join(map(str,t['numbers']))+'|'+pct(t['p'])+'|'+pct(t['cumulative'])+'|')
                lines+=['']
            probabilities={h['number']:h['p1'] for h in m['horses']}
            joint={}
            for i,j,k in itertools.permutations(probabilities,3):
                pi,pj,pk=[probabilities[n] for n in (i,j,k)]
                joint[i,j,k]=pi*pj/(1-pi)*pk/(1-pi-pj)
            wide={pair:sum(p for triple,p in joint.items() if set(pair)<=set(triple)) for pair in itertools.combinations(sorted(probabilities),2)}
            choices=sorted(wide,key=lambda pair:(-wide[pair],pair))[:3]
            lines+=['ワイド上位3点（参考）','','|買い目|個別確率|重複除外後の合計|','|---|---:|---:|']
            for count,pair in enumerate(choices,1):
                union=sum(p for triple,p in joint.items() if any(set(candidate)<=set(triple) for candidate in choices[:count]))
                lines.append('|'+ '–'.join(map(str,pair))+'|'+pct(wide[pair])+'|'+pct(union)+'|')
            lines+=['','</details>']
    lines+=['','モデル重み・稼働モデル・研究バージョンは変更していません。騎手のコース別適性、馬との相性、海外成績を新たに追加したものではありません。馬連・ワイド・3連複の現在オッズとEVに基づく配分は未計算です。']
    return '\n'.join(lines)+'\n',quotes

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for key in ('prediction','evidence','output','quotes'):p.add_argument('--'+key,required=True)
    a=p.parse_args();text,quotes=render(json.loads(Path(a.prediction).read_text()),json.loads(Path(a.evidence).read_text()))
    for path in (a.output,a.quotes):
        if Path(path).exists():raise ValueError('immutable output exists')
    Path(a.output).write_text(text);Path(a.quotes).write_text(json.dumps(quotes,ensure_ascii=False,indent=2)+'\n')
