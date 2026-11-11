# V51・新4軸特徴量の実装／厳格な事前情報検証（2026-11-11）

## 目的と守るべき境界

正式版は **V51** のまま。旧V50へ戻さず、`operations/prediction_policy/standard_v51_model.json` の正式31特徴量・係数・2025校正値は一切改変しない。

追加候補：①過去の相手クラス・相手実力、②過去の4角通過順位／脚質、③競馬場・芝ダート・距離条件別騎手成績、④馬体重の発表時刻・増減率。

根拠はJRA一次資料：
- [クラス分け](https://www.jra.go.jp/keiba/rules/class.html)：GI/GII/GIII/リステッド/オープン/3勝/2勝/1勝/新馬・未勝利。
- [年度別全成績の見方](https://www.jra.go.jp/datafile/seiseki/report/mikata4.html)：過去レースのコーナー通過順位、馬体重・増減の記載ルール。
- [年度別PDF索引](https://www.jra.go.jp/datafile/seiseki/report/2026.html)：年度別全成績PDFは「開催の翌日に掲載」。**翌日何時に公開されたかは、この文言だけでは証明できない。**
- [当日馬体重の掲載](https://www.jra.go.jp/faq/pop02/2_13.html)：JRAのレース欄に「発表済」が出た場合に確認可能。発表後、出馬表にも反映される。固定で「発走X分前」と推定しない。
- [出馬表の発表日時](https://www.jra.go.jp/faq/pop02/2_2.html)：通常は木曜16時過ぎに仮出馬表、前日10時過ぎに枠・馬番号つき発表。重賞の一部には例外あり。

## 実装

| 対象 | 入力条件と変換 | 欠測時 |
|---|---|---|
| 相手クラス／実力 | 過去の公式クラス表記を0〜9の順序指標へ。相手実力は当該過去レースの**レース前時点**の他馬の過去勝率を集約（次走以降のみ） | 必ず欠測フラグ。曖昧なレース名から決めつけない |
| コーナー位置・脚質 | 過去レースの4角通過順位から正規化順位・先行率・4角からゴールへの順位改善量を計算 | 通過順の記載が無ければ欠測。着順から4角位置を捏造しない |
| 条件別騎手 | 同一競馬場×芝/ダート×距離差200m以内の実績。母集団の3着以内率への20仮想標本の縮約を行い、差分を抽出 | 騎手ID未確認や同条件出走ゼロなら欠測 |
| 馬体重 | 直近の**過去レース**に記載された増減率は次走以降のみ利用。当日の体重はJRA「発表済」かつ実測 `published_at <= observed_at <= forecast_asof < race_off` の場合のみ算出 | 当日未発表・時刻不明は欠測、0kgにはしない |

### 1. 発走前の検証可能な特徴量

- `scripts/v51_four_axis_preoff_research.py`：出走馬の公式馬ID証拠と、過去結果の公開時刻・取得時刻・発走時刻をチェック。時系列逆転、将来結果、別馬／別騎手履歴、発表前馬体重は拒否。出走馬全頭の同一 `forecast_asof` で出力。
- `tests/test_v51_four_axis_preoff_research.py`：クラスパーサ、前走の位置取り、条件別騎手、発表済486kg(+8kg)、未発表、未来発表、馬IDの取り違え等を回帰テスト。**テストの数字は合成例であり、現実の的中率ではない。**

### 2. 正本v12・実データの入力可能率を監査

- `scripts/v51_four_axis_canonical_coverage.py`：Libraryの正本 `jra_2023_2025_v12_horse_ids_full_20261111.sqlite`（SHA256 `5d16777588420ac88bab5df21defb85d9346c2b918bb71859af06893752bcadd`）で `PRAGMA quick_check`、実保存カラム／JSONキーとクラス・コーナー・馬体重・騎手IDの存在件数を計数する。
- 正本には結果PDF由来の `body_weight_raw`／`body_weight_change_raw` があることは既存の[監査](../v51_body_weight_real_audit_20261109.md)で実測済み。ただし当日の**発表前時刻を復元できるわけではない**。
- `scripts/v51_repository_source_schema_probe.py` はGitHubに実在する小規模2026年SQLiteを調べる補助コード。正本v12の検証と混同しない。

### 3. 追加特徴量から順位モデルを再学習する研究設計

- `scripts/v51_four_axis_historical_features.py`：既存の31特徴量と同じ `race_id × horse_number` で14特徴量を生成。**過去成績が掲載翌日に発行される資料であることを踏まえて、公開時刻未証明の回顧実験では過去2暦日以上の履歴だけに限定**。この2日制約は保守的な研究仮定で、当時公開された証拠そのものではない。
- `scripts/v51_four_axis_rank_residual_study.py`：既存31特徴量・正式モデルの全係数は固定。2023/24で新14特徴量の1着順位への加算残差だけ学習。クラス・相手／脚質／騎手／過去馬体重とその組合せでRidge 0.03/0.10を比較。2025日付順の前期40%で確率校正、中期40%で候補選択、後期20%で採否判定、**2026は候補確定後に限り監査**。
- 最低条件：2025後期で1着指名的中率の開催日ブロック・ペア95%CI下限が0超、Log Loss改善、Brier/ECE非悪化。満たさなければ正式V51は不変。2/3着ステージは今回の加算残差学習では変更しない。
- 過去レースの体重は**過去情報**として使えるが、当該レースの結果PDFに掲載された体重を当該レースの「発走前体重」として流用しない。実体重の発表時刻が無い2023–2026年への後付け学習も禁止。

## 再現用コマンド

```bash
python -m scripts.v51_four_axis_canonical_coverage \
  --database /data/jra_2023_2025_v12_horse_ids_full_20261111.sqlite \
  --output /data/v51_four_axis_source_coverage.json

python -m scripts.v51_four_axis_rank_residual_study \
  --database /data/jra_2023_2025_v12_horse_ids_full_20261111.sqlite \
  --review-overlay /data/jra_review_1975_verified_v2_20261111.sqlite \
  --historical-feature-script scripts/jra_historical_horse_id_ablation.py \
  --model operations/prediction_policy/standard_v51_model.json \
  --output-dir /data/v51_four_axis_rank_study
```

出力 `v51_four_axis_2025_rank_research_report.json` と `v51_four_axis_2025_research_proposal.json` を対象。候補モデルは常に `production_enabled=false`、ソース・特徴量・時系列・採否の根拠を保持。

## 実SQLiteを読み取った2026年11月8日データの追加監査

根拠: `reports/v51_four_axis_existing_2026_source_schema_audit_20261111.json`、GitHub Actions [43025062191](https://github.com/tashiroshuma-bit/keiba-ai-data/actions/runs/43025062191)。

- `operations/data_updates/jra_official_20261108_all_runner_history_v2.sqlite`：**36レース、497頭**（正本v12とは別データ）。
- 497件すべてに公式馬ID・コーナー通過順欄・取得時刻・ソースURL・SHA256。
- **419件**に過去結果として馬体重と増減、残り78件は欠損。
- 当該データの `source_race` に公式クラス列、`runner_postrace` に騎手ID列はなく、ここから「クラス」や「騎手能力」を単独で埋めることは不適切。
- 当初の通過順は `'2 2'`、`'3 4'` など空白区切りであり、列の「存在」だけで数値化を主張できなかった。実表記を取得してパーサーを修正した。
- パーサー修正後の実レコード監査：[GitHub Actions 43026236465](https://github.com/tashiroshuma-bit/keiba-ai-data/actions/runs/43026236465)、`reports/v51_real_nov08_history_next_start_20261114_asof_audit_20261111.json`。**497/497頭の過去通過順を数値化、419/497頭の過去馬体重増減率を数値化、未取得78頭は欠損として保持**。将来の2026年11月14日8時のasofを仮定した参照可否で、11月14日の実出走馬の照合はまだ行っていない。
- 数値化した過去4角相当の正規化位置平均は0.46539（0は先頭・1は最後尾）、過去体重増減率の平均は+0.25584%（有効419頭）。どちらも**説明統計であり、V51の予測精度上昇ではない**。
- `scripts/v51_real_20261108_next_start_history_audit.py` は、実行済み `query_jra_official_past_runs_asof.py` と同じ2暦日制約、当時の `observed_at` により**11月8日より後の予測時点**からのみ過去位置・過去増減率を利用する。2026/11/08自身の発走前予測には**使用禁止**。
- 「取得時刻」は当時情報が確認できたことの証拠だが、公式サイトの正確な初回公開時刻ではない。両時刻を同一視しない。

## 実行状態と事実

2026年11月11日時点で、新しい発走前入力バリデーション・過去データ抽出・特徴量生成・残差学習プログラムおよび各ユニットテストをGitHubへ実装。GitHub Actionsの合成テストで発生した過去馬体重名の食い違いとPython式の改行バグを修正。

一方、このチャットのローカルPython/コンテナが `ClientError` のため、**Libraryの362MB正本を使用した今回の新14特徴量について全件のカバレッジ集計・2025順位精度の実測比較は未完了**。以前のPR #30にある2026年1着603/2,411（25.01%）、順不同6.01%、順序一致1.33%は旧31特徴量の測定値であり、今回の新特徴量が向上させた結果ではない。数値を捏造せず、正式V51を維持する。
