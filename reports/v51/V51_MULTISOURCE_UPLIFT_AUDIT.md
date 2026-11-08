# V51：4サイト補助DBの実データ効果検証

判定：追加の馬別特徴量0件。V51の的中率改善は算定不能。正式v50維持。

|対象|実測|
|---|---:|
|提供元登録|5|
|JRA結果レース|36|
|隔離不一致|1|
|馬別特徴量|0|
|発走前として確認済みの特徴量|0|
|発走前全頭特徴量が完備したレース|0|
|同一時刻のv50/v51直接検証可能レース|0|

## 根拠と解釈

GitHub保存済みSQLiteのSHA256・全テーブル件数・整合性を直接再検査した。
JRA公式のレース結果36Rは正しい教師ラベルであるが、血統・騎手・走破内容・調教の追加事前特徴量ではない。
過去の研究V51候補は2025・2026の両年で全評価指標を改善していない。追加ソース0件を新学習成功と表現しない。
利用権限がない他サイトの大量抽出・契約回避は実施しない。
次に必要なのは使用許可と公開時刻を確認できる全出走馬の公式ID・事前特徴量・同一時刻のV50/V51凍結予測。

## データの参照先

- operations/data_updates/multisource_overlay_20261108.sqlite
- operations/data_updates/multisource_overlay_20261108_audit.json
- operations/predictions/2026-11-07/v50_weekend_abcd_reconnected.json
- operations/results/2026-11-08/v50_abcd_settlement.json
- operations/prediction_policy/v51_candidate_fitted_research.json

