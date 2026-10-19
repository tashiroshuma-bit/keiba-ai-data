# JRA年度別全成績の取り込み

対象：2023・2024・2025年、各年288件の公式開催日PDF、計864件。
取得元は `https://www.jra.go.jp/datafile/seiseki/report/{year}.html`。
重賞専用PDFと異なり、一般競走を含む年度別全成績を対象とする。

## 実行

```bash
python -m pip install -r requirements.txt
python keiba_v48/annual_reports.py --db jra_2023_2025.sqlite --cache annual_pdf_cache
python keiba_v48/annual_parser.py --db jra_2023_2025.sqlite
python keiba_v48/annual_export.py --db jra_2023_2025.sqlite --output annual_output
```

取得とDBへの抽出は上の順序で実行し、同じDBに対して同時実行しない。
ダウンロードは最大4並列。取得済みPDFは再利用し、SHA256と取得時刻を保存。
既存の`races/documents/runner_results`は変更しない。

## 追加テーブル

- `annual_report_documents`：出典、年・開催、チェックサム、取得・処理状況。
- `annual_report_races`：レースID、開催日、発走予定時刻、距離・馬場、頭数、検証理由、抽出した原文。
- `annual_report_runners`：馬番、枠番、掲載順、馬・騎手名、重量、タイム、最終単勝オッズ。
- `annual_result_labels`：結果照合用のSQLビュー。export実行時に作成。

`race_id`は年・競馬場コード・開催回・開催日・レース番号から作る開催内の識別子。
馬ID・騎手IDとは別であり、馬名から公式登録IDを捏造しない。

## 検証と使い分け

`validated_result`は、表の頭数・馬番重複・必要なレース情報・単勝払戻と勝馬オッズの一致などの**自動照合通過**を示す。公式ID検証済み・人手確認済みという意味ではない。

同着、取消、中止、除外、頭数不一致、未解決の数字や図形文字を含むレースは`requires_review`へ隔離する。`finish_order`は掲載順を保存し、要確認レースの`finish_position`は空欄にする。

数字はAdobe Japan1のCID9872～9881を復元する。図形化された数字は埋め込みフォントの輪郭と照合して復元し、輪郭の開始点・描画方向・正規化時の丸めの差だけを許容する。一意に照合できない図形は数値へ推測変換しない。図形文字の復元を含むレースは、人手確認前の学習利用を禁止する。レース番号が読めずページ順から候補を作った場合も必ず要確認と明記する。

出力CSVの`final_win_odds`は確定後の結果データ。`pre_off_odds/odds_timestamp`は空欄のままで、発走前オッズとして流用しない。

`observed_at`は今回の取得時刻であり、過去の結果公表時刻ではない。`horse_id/jockey_id/result_available_at`が揃うまでは`model_history_eligible=no`を維持する。この制約により、データ取得・結果表への取り込み完了と、v4.8への学習投入完了を明確に区別する。

PDF原本はキャッシュ、原文と出典・SHA256はDBに保持する。レース単位の取りこぼし、取消に伴う開催の変則例などは、`annual_ingest_audit.json`のエラー・要確認理由で追跡する。

## テスト

```bash
python -m unittest discover -s keiba_v48 -v
python -m compileall -q keiba_v48
```

合成データの機能テストとは別に、実PDFを全件処理して頭数などを照合する。公式成績を学習データと結合した予測精度・回収率の検証は、この取り込み処理の完了とは別工程。
