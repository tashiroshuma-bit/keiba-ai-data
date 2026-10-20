# 競馬予想AI v4.8 — 統合入口

開発・データ修復・予想・結果検証の共通入口です。別スレッドや古いZIPから作業を再開する場合も、最初に最新mainの [DEVELOPMENT_HANDOFF.md](DEVELOPMENT_HANDOFF.md) と [PROJECT_STATE.json](PROJECT_STATE.json) を確認してください。

| 対象 | 正本 |
|---|---|
| コード・変更履歴 | このリポジトリのmain |
| 現在のデータ・モデル・未解決課題 | [PROJECT_STATE.json](PROJECT_STATE.json) |
| 最新の実測検証 | [回収率95%目標の検証](keiba_v48/ROI95_RESULTS.md) |
| 採用判断 | [95%目標検証後の判定](keiba_v48/reports/roi95/adoption_review.json) |
| 保存成果物の一覧 | [成果物台帳](keiba_v48/reports/integration/artifact_registry.json) |
| 旧上位3着モデル・馬券精算 | [診断専用コード](research/legacy_20261007/INTEGRATION.md) |

2026-10-20：結果オッズを使う回顧研究で、2024年だけで選択したルールの2025年回収率が96.69%／104.21%（公開2日後／7日後仮定）となり、点推定の95%目標へ到達しました。対象3,314レース、仮想購入1,937件／1,870件。将来の95%維持・発走前運用は未証明で、稼働重みと購入生成無効を維持します。構造のみの固定345レース49.39%とは情報条件・対象が異なります。DB version 8、利用可能10,056レース、除外309レースは変わりません。

リポジトリ直下の `jra_2023_2025.sqlite` は初期取り込み用の小さな過去ファイルです。最新の26万KB級の修復DBではありません。名前が同じでも正本として使わず、台帳の保存ID・版・SHA256を照合してください。

```bash
python -m pip install -r requirements.txt
python scripts/project_status.py
python -m unittest discover -s keiba_v48 -v
```

統合状態の整合性検査に加え、DBを手元に取得した場合は `python scripts/project_status.py --db /absolute/path/jra_2023_2025.sqlite` でSHA256とSQLiteの整合性も検査できます。

この統合はコード・保存成果物・タスク参照の一本化です。チャットのメッセージそのものを移動・結合する操作は行っていません。会話横断検索は失敗したため、未保存の会話内だけの変更まで確認できたとは扱いません。
