# v50: A〜D 保存予測から全頭確率を出す

## 実装経路

1. 従来の発走前A〜D予測JSON（`created_at`, `races[].models.A.horses[].p1`,
   `races[].runners[].jockey_id`, `off_at`, `surface`）を準備する。
2. 発走前の正本SQLiteを利用できる場合、正式経路の
   `scripts/standard_v50_forecast.py` を使用する。正本DBのSHA確認必須。
3. SQLiteを直接読めず、過去に保存・検証した騎手残差スナップショットを使う研究経路では:

```bash
python -m scripts.v50_from_abcd \
  --saved-abcd reports/<date>/PREDICTIONS.json \
  --riders reports/v50/horse_adjusted_rider_snapshot_20261029.json \
  --output operations/predictions/<date>/v50_research.json
```

出力: `races[].v50.horses[].p1/p2/p3`（全頭）、`marks`、
`ordered_top3`、`priority.single/quinella/trio`（組合せ確率と累積）、
`top5_by_date`（1着最高確率上位5レース）、各馬`A_p1`（比較用）。

**注意:** 本経路は既存のA確率をv50騎手残差+T=0.7で変換する。
B/C/Dは再計算しない。Aの入力が欠けると新しい勝率を捏造せず中止。
出走馬の馬番・馬名を照合し、発走後の入力を拒否する。
障害は騎手残差の対象外としてスキップ。
`--allow-historical` は明示的な遡及研究であり、本番予測を意味しない。
研究経路の出力は`standard_forecast=false`、新しい実績検証が必要。

前日（2026-11-07〜08）の全72Rをこの変更だけで算出したとは扱わない。
当日の実出馬表と、同日のA〜D確率が保存されて初めて実行できる。

## テスト

`python -m unittest discover -s tests -p 'test_v50_from_abcd.py' -v`

既存の `.github/workflows/main.yml` は
`python -m unittest discover -s tests -p 'test_v50*.py' -v`
を実行するため、変更のPR/pushで対象テストを含める。
