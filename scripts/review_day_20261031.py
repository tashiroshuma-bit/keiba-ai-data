"""Score immutable rider forecasts against cross-checked results; no refitting."""
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRED = ROOT/'reports/weekend_20261031_1101/ALL_FLAT_RIDER_RECALC_20261031T033252.json'
RESULT = ROOT/'operations/results/2026-10-31/DAY_RESULTS_REVIEW_20261031.json'
OUT = ROOT/'reports/review_20261031'
FOCUS = ['東京10R','東京7R','京都10R','東京11R','東京9R','京都11R']


def evaluate(race, result, letter):
    horses = sorted(race['models'][letter]['horses'], key=lambda h: (-h['p1'], h['number']))
    order = [h['number'] for h in horses]
    actual = [n for _, n in result['top3']]
    if len(actual) != 3 or len(set(actual)) != 3:
        raise ValueError('unique top three required')
    if not set(actual) <= set(order):
        raise ValueError('result runners absent from freeze')
    probability = {h['number']:h['p1'] for h in horses}
    place = max(horses, key=lambda h: (h['p1']+h['p2']+h['p3'], -h['number']))
    top = order[:3]
    return dict(race=race['race'], model=letter, actual=actual,
        top1=order[0], top3=top, top1_hit=int(order[0]==actual[0]),
        unordered_hit=int(set(top)==set(actual)), ordered_hit=int(top==actual),
        capture_count=len(set(top)&set(actual)),
        winner_probability=probability[actual[0]],
        top1_probability=horses[0]['p1'],
        winner_model_rank=order.index(actual[0])+1,
        place_pick=place['number'], place_hit=int(place['number'] in actual),
        place_probability=sum(place[k] for k in ('p1','p2','p3')),
        # Payout per 100 yen is a reference, not an actual purchase/ROI.
        place_payout_100_reference=result['payouts']['place'].get(str(place['number']),0),
        log_loss=-math.log(probability[actual[0]]),
        brier_sum=sum((p-int(n==actual[0]))**2 for n,p in probability.items()),
        selected_ticket_hits={kind:any(
            '-'.join(map(str,t['numbers'])) in result['payouts'][kind]
            for t in saved['tickets'])
            for kind,saved in race['models'][letter]['priority'].items()})


def summarize(rows):
    n=len(rows)
    return dict(races=n, **{key:sum(r[key] for r in rows) for key in
        ('top1_hit','ordered_hit','unordered_hit','place_hit','capture_count')},
        top1_hit_rate=sum(r['top1_hit'] for r in rows)/n,
        place_hit_rate=sum(r['place_hit'] for r in rows)/n,
        capture_rate=sum(r['capture_count'] for r in rows)/(3*n),
        log_loss=sum(r['log_loss'] for r in rows)/n,
        brier_sum=sum(r['brier_sum'] for r in rows)/n,
        mean_top1_probability=sum(r['top1_probability'] for r in rows)/n,
        mean_place_probability=sum(r['place_probability'] for r in rows)/n)


def main():
    freeze=json.loads(PRED.read_text()); actual=json.loads(RESULT.read_text())
    result={r['race']:r for r in actual['races']}
    races=[r for r in freeze['races'] if r['date']=='2026-10-31']
    assert len(races)==23 and len(result)==24
    rows=[evaluate(r,result[r['race']],m) for r in races for m in 'ABCD']
    summaries={m:summarize([r for r in rows if r['model']==m]) for m in 'ABCD'}
    focus={m:summarize([r for r in rows if r['model']==m and r['race'] in FOCUS]) for m in 'ABCD'}
    payload=dict(schema='immutable-day-review-v1', forecast_sha256=hashlib.sha256(PRED.read_bytes()).hexdigest(),
        results_sha256=hashlib.sha256(RESULT.read_bytes()).hexdigest(),
        scope='23 flat races, not selected winners; Kyoto4R obstacle outside prediction domain',
        official_verified=False, production_forward_added=0, model_retrained=False,
        actual_bets=False, actual_roi=None, summaries=summaries, afternoon_six=focus, scores=rows)
    OUT.mkdir(exist_ok=True)
    (OUT/'scores.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
    lines=['# 10/31 全レース振り返り・次回の修正','',
        '東京12レース＋京都12レースの全24レースの上位3頭と単勝・複勝・馬連・ワイド・3連複・3連単の払戻をnetkeibaとスポーツナビで照合。公式の全件直接照合は未完了。順位評価は保存予測のある平地23Rが分母、障害京都4Rは対象外。',
        '予測元は騎手反映後の固定JSON。直前更新でも確率は不変。過去の予測を結果に合わせて上書きせず、正式forward実績・実収支には計上しない。', '',
        '|モデル|本命1着|順不同3頭完全一致|1〜3着順序完全一致|上位3頭捕捉|複勝1点候補|',
        '|---|---:|---:|---:|---:|---:|']
    for m,s in summaries.items():
        lines.append(f"|{m}|{s['top1_hit']}/23（{100*s['top1_hit_rate']:.2f}%）|{s['unordered_hit']}/23|{s['ordered_hit']}/23|{s['capture_count']}/69|{s['place_hit']}/23（{100*s['place_hit_rate']:.2f}%）|")
    lines+=['','複勝候補は各モデルの3着以内推定が最大の1頭。全23Rで同じルールを事後採点した診断であり、全23Rへの事前購入推奨や実購入を意味しない。',
        '', '|モデル|平均本命勝率|実際の本命1着率|Log loss|Brier（全馬合計のレース平均）|', '|---|---:|---:|---:|---:|']
    for m,s in summaries.items():
        lines.append(f"|{m}|{100*s['mean_top1_probability']:.2f}%|{100*s['top1_hit_rate']:.2f}%|{s['log_loss']:.4f}|{s['brier_sum']:.4f}|")
    lines+=['','1日23Rだけで校正済みとは判断せず、結果に合わせた混合率変更・係数調整は行わない。', '',
        '## このチャットで提示した午後ベスト5＋重賞','',
        '|レース|確定上位3頭|A複勝候補|結果|100円当たり参考払戻|','|---|---|---|---|---:|']
    for name in FOCUS+['東京12R']:
        r=next(r for r in rows if r['race']==name and r['model']=='A')
        lines.append(f"|{name}|{'→'.join(map(str,r['actual']))}|{r['place_pick']}|{'的中' if r['place_hit'] else '不的中'}|{r['place_payout_100_reference']}円|")
    lines+=['','東京12Rは東京7R終了後の追加枠で、当初6Rに混ぜず別記。午後6RのA複勝は'+str(focus['A']['place_hit'])+'/6。', '',
        '## 問題と修正','',
        '- 京都11R：A本命⑪ツキミは11着。Aの3着以内66.78%と大きく外れた。馬体重438kg・増減0でも不的中で、増減だけでは説明できない。D本命③も9着。実際の3着⑤バタフライはA11番手。馬・騎手の簡易値、近走・展開・穴の評価を改善する課題。',
        '- 東京10R：A本命③は2着、勝馬⑦はA2番手。単勝失敗と複勝成功を区別。3着①ケイケイは+18kgでも好走。大幅増を機械的に減点しない。',
        '- 京都10R：本命⑨は3着、勝馬③はA8番手。軸の複勝成功と勝馬の低評価を分ける。',
        '- 現行の当日馬場項目は係数0、馬体重は確率モデル入力未実装。観測値を表示しただけで「補正済み確率」と呼ばない。',
        '- 次回から馬体重・増減kg・前走比率・過去同馬の観測範囲・休養間隔を必ず参照。初出走・欠測は別扱い。出典と実観測時刻を検証し、結果画面から拾った値は発走前に混ぜない。',
        '- 直前値が未確認なら暫定表示を維持。全頭の有効な発走前観測が揃わなければ「直前確認済み」の出力を拒否する。馬体重による確率修正は学習・時点分割検証ができるまで保留し、適性の参考と確率計算の利用状況を分けて表示。',
        '- 全組み合わせに当たりが含まれることを推奨買い目の的中と数えない。モデル間で本命が違う場合は一致を装わない。', '',
        '## 全23R・4モデル','', '|レース|結果|A指名／上位3捕捉|B指名／上位3捕捉|C指名／上位3捕捉|D指名／上位3捕捉|', '|---|---|---|---|---|---|']
    for race in sorted(races,key=lambda r:(r['track'],r['race_number'])):
        rr=[next(r for r in rows if r['race']==race['race'] and r['model']==m) for m in 'ABCD']
        lines.append('|'+race['race']+'|'+'→'.join(map(str,rr[0]['actual']))+'|'+'|'.join(f"{r['top1']}{'○' if r['top1_hit'] else '×'}／{r['capture_count']}頭" for r in rr)+'|')
    lines+=['','[全数値・固定予測ハッシュ](scores.json) ／ [照合結果原簿](../../operations/results/2026-10-31/DAY_RESULTS_REVIEW_20261031.json) ／ [次回の馬体重参照ルール](../../operations/PREOFF_BODY_WEIGHT_POLICY.md)', '',
        '出典： [東京・netkeiba](https://race.netkeiba.com/top/payback_list.html?kaisai_date=20261031&kaisai_id=2026050410) ／ [東京・スポーツナビ](https://sports.yahoo.co.jp/keiba/race/list/26050410) ／ [京都・netkeiba](https://race.netkeiba.com/top/payback_list.html?kaisai_date=20261031&kaisai_id=2026080410) ／ [京都・スポーツナビ](https://sports.yahoo.co.jp/keiba/race/list/26080410)']
    (OUT/'REVIEW.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'summaries':summaries,'afternoon_six':focus},ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
