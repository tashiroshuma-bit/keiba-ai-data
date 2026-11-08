# 2025年過去351レース｜東京11R級・超大波乱の頻度と予兆分析

**超大波乱＝3着以内の全3頭が最終7番人気以下**。単に4番人気以下が勝ったレースと混同しない。
定義は11月8日を確認した後の探索的な研究定義。2025年検証への転用は事後的であり将来性能を保証しない。
2025実データ照合 351/351レース、超大波乱 1R (0.28%)。
拡張型（10番人気以下勝利、かつ7番人気以下2頭以上が入着）13R。
2026-11-08平地34Rで超大波乱 1R（東京11R）。
開催日で分割：学習226R（2025-07-26まで）、検証125R（2025-07-27以降）。

## 2025年・超大波乱が起きた開催場

|場所|レース数|
|---|---:|
|京都|1|

## 予測前に使える候補条件の検証

- 出走頭数
- 当時保存された予測の1着トップ確率
- 予測1位と2位の確率差
- 予測確率の正規化エントロピー

候補ルール：学習データでもサポート要件を満たすルールなし。
学習結果：該当なし。
時系列未学習データ：該当なし。
独立検証を満たし適用可：**False**。
満たさない場合は必ず**通常v50を維持**し、波乱補正しない。大波乱の的中を約束するモードは作らない。

## 制約・解釈

- Final popularity determines historical labels only; never model input.
- 2025 frozen candidate score is a different model from canonical v50; transferable rule not proven.
- Sample is a selected 351-race cohort, NOT all JRA 2025 races.
- Extremely rare events have unstable confidence intervals; no model activation absent sufficient holdout support.
