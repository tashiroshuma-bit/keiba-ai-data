# 競馬予想AI v4.8：10項目の実装

最新の修復・悪化診断・再検証は **[OFFLINE_REPAIR_RESULTS.md](OFFLINE_REPAIR_RESULTS.md)**。確率改善を確認、収益改善条件は未達。本番重みを維持。

最新の追加実装・396レース比較・本番昇格見送りは **[COMPLETION_RESULTS.md](COMPLETION_RESULTS.md)** を参照。以下の旧記録と区別してください。

既存の市場基準モデル・PDF収集処理を維持し、`improvements.py` を新しい学習・推論の入口にした。
**実装テストと予測精度の検証は別。実データでの改善成績は未確認。**

| 項目 | 実装内容 | 主なファイル |
|---|---|---|
| ① 全走歴統合 | 重賞・非重賞CSVを複数投入。レース×正規化馬IDで統合し、重複除去・競合停止。直近4走に限定しない | features.py |
| ② モデル階層化 | 全体の係数＋競馬場/芝ダート別の係数偏差。偏差に強いL2正則化。未観測コースは全体へ縮約。市場オッズを構造モデルの特徴量に含めない | fitted_model.py |
| ③ 勝率校正 | 学習期間より後の独立期間でtemperatureを選択。学習との重複・校正ラベルより前への推論を禁止 | fitted_model.py |
| ④ 馬・騎手ID統一 | `jra:登録番号` 等の名前空間付きID。別IDの統合には確認済み対応表と出典URLが必須。名前から推測結合しない | features.py |
| ⑤ 近走の質 | 近3走の頭数正規化着順＋クラス補正、休養日数、負担重量変化、同条件の相対速度。欠測は観測件数・フラグで区別 | features.py |
| ⑥ コース・馬場適性 | 同競馬場/路面・近似距離・馬場状態の3着内成績を縮約。現時点の馬場が不明なら馬場順位を表示しない | features.py, improvements.py |
| ⑦ 展開・脚質 | 過去の4角位置・上がり順位を別特徴量化。スロー/平均/ハイの全頭分布を固定重みで混合し、1/2/3着・ワイド・3連複を算出 | strategy.py |
| ⑧ 発走前オッズ・期待値 | 締切前かつ鮮度60分以内の全頭単勝オッズ。ワイド/3連複は組み合わせ別の時刻付き実オッズのみ。期待値と勝率を分離 | strategy.py |
| ⑨ 収益リスク管理 | 不確実性による確率割引、保守的期待値基準、1/4 Kelly、100円単位、1レース・総建玉の上限、見送り理由。実払戻で精算しROIと最大DDを計算 | strategy.py, validation.py |
| ⑩ 継続検証 | SQLite追記専用予測・精算台帳。モデル/特徴量/入力/買い目固定、forward/replay区分。同一レースの市場基準比較、Log Loss/Brier、勝率/3着内校正、レース単位bootstrap | validation.py, improvements.py |

4軸（勝率・単勝期待値・馬場適性・3着確率）を出力し、全頭に購入採用/除外理由を保存する。3着確率はPL着順分布に基づく近似で、独立した学習済み3着モデルではない。

## 入力契約

`v48_history_template.csv` と `v48_runners_template.csv` はヘッダーのみのテンプレート。
CSVは文字列IDを維持して読み込む。レースIDは全入力で同じID体系を使用する。

- 履歴の必須列：`race_id,horse_id,jockey_id,off_timestamp,result_available_at,source_url,distance_m,surface`。対象レースの結果や締切後に判明した履歴は特徴量から除外。
- 追加履歴列：`finish_position,field_size,class_level,track,going,carried_weight,corner4_position,last_3f_rank,relative_speed_z`。クラスは0=未勝利、1=1勝、2=2勝、3=3勝、4=OP/G3、5=G2、6=G1の固定序数。これは設計上の補正であり、最適性は未検証。
- `relative_speed_z` は同レース・同条件の比較対象で計算した速度の標準得点（高いほど速い）。生タイムをコース間で直接比較しない。取得できなければ空欄。
- 出走表は取消を除いた全頭が必要。各行に`field_complete=yes`と`source_url`、重複しない正の馬番、同一の発走時刻/競馬場/路面/距離が必要。
- `going`は予測時点の馬場。入力する場合`going_asof`必須。現時点の重量を入力する場合`features_asof`必須。結果から転記して発走前に知っていたことにしない。
- 全時刻はタイムゾーン付きISO8601。締切は発走5分前。履歴の`result_available_at`を発走時刻から推測補完しない。
- IDの名前空間は出所を表すだけで、公式IDの検証済み証明ではない。対応表CSVは`kind,alias,canonical,verified,source_url`。`kind`は`horse`/`jockey`、`verified=yes`は利用者による照合済みの宣言。
- 学習/評価用出走表は全頭の`finish_position,result_available_at`も必要。同着・競走中止は現在対応していないため、対象レースを明示的に除外する。
- 過去の最終オッズは発走前オッズの代用にしない。欠損/古いオッズでは確率は出力するが全購入を見送る。

## 実行

リポジトリのルートで実行：

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s keiba_v48 -v
python keiba_v48/improvements.py train --history graded.csv nongraded.csv --runners training_fields.csv --model model.json
python keiba_v48/improvements.py predict --history graded.csv nongraded.csv --runners current_field.csv --model model.json --ledger predictions.sqlite --output prediction.json --bankroll 100000 --race-budget 5000 --open-exposure 0
python keiba_v48/improvements.py evaluate --history graded.csv nongraded.csv --runners evaluation_fields.csv --model model.json --output comparison.json
python keiba_v48/improvements.py settle --ledger predictions.sqlite --prediction-id ID --result result.json
```

学習は2023年・校正は2024年が既定。変更は`--train-year`/`--validation-year`。2025年は既に検討済みなので**探索的参考**であり未見テストとは呼ばない。今後100レース以上を目安に締切前の予測固定・前向き比較を行う。

過去時点の再現は`predict --mode replay`。実行時刻が締切後なら`forward`保存を拒否する。台帳に実行時刻、モード、モデル本体とハッシュ、全頭特徴量、当時のオッズと出典、購入設定を残す。通常APIでの上書き/削除はDBトリガーで禁止（DB所有者に対する改ざん耐性を保証する仕組みではない）。

購入は全て`mode=virtual`。実購入との接続は含めない。既定の上限は「指定予算・残高の2%・総建玉10%から既存建玉を引いた額」の最小値。残高10万円・予算5000円なら上限2000円。保守的期待値1.05未満は見送り。これらは運用上の初期設定であり、収益を確認した最適値ではない。

ワイド・3連複は`--quotes quotes.json`を追加：

```json
[{"race_id":"対象レースID","kind":"wide","horse_numbers":["1","2"],"decimal_odds":5.2,"odds_timestamp":"2026-10-25T15:30:00+09:00","source_url":"https://出典"}]
```

`kind`は`wide`または`trio`。ワイドがレンジ表示なら下限を保守的に使用する。組み合わせ別オッズがない券種を推測生成しない。

精算JSON：

```json
{"race_id":"対象レースID","finishes":{"1":1,"2":2,"3":3},"result_available_at":"2026-10-25T16:00:00+09:00","source_url":"https://公式結果出典","payouts_per_100":{"win:1":250,"wide:1,2":400,"trio:1,2,3":1200}}
```

馬番キーは数値昇順。払戻は100円当たりの実払戻金。的中券の払戻欠損は未精算としてROIから除外し、未精算レース数を併記する。`equity_report`にはレース時刻順に精算を渡す。引分け・返還・取消後の再精算は未対応。

## 検証結果と限界

- 追加テストは合成データ。学習→校正→予測→評価CLIも通して検証。実データの的中率・回収率を示すものではない。
- 全走歴統合は投入CSVの範囲。これにより全JRAデータの取得完了を意味しない。リポジトリ同梱DBは1レース/18頭で、馬・騎手IDと発走前オッズ履歴を持たない。PDFからそれらを捏造補完しない。
- 展開の重みは各1/3の感度分析仮説で、学習済み展開確率ではない。位置取り・路面・時計/内外の当日バイアスを結果から後付け推定しない。今回、当日の内外バイアス推定モデルは追加していない。
- 不確実性割引は経験則で、統計的信頼下限ではない。PLのIIA仮定や組み合わせ間の相関の限界があり、資金上限で制約する。
- `evaluate`は同じ全頭・同時刻の市場基準と比較。旧v4.7の固定予測は同梱されていないため、旧モデルとの比較結果は捏造しない。`paired_report`に同一レースの旧予測を与えれば比較可能。
- 現時点の評価は勝率Log Loss・Brier・Top1と3着内校正。人気帯別の外部検証・特徴群を外して再学習する増分検証・実データでの収益優位性は今後のデータ整備後に行う。
- `.github/workflows/main.yml`は誤って保存されていたシェルスクリプトを有効なCIへ修正。`--index-dir`で欠損HTMLがある場合に外部アクセスへ切り替わる不具合も修正。
