# 競馬予想AI v4.8 — 統合入口

開発・データ修復・予想・結果検証の共通入口です。別スレッドや古いZIPから作業を再開する場合も、最初に最新mainの [DEVELOPMENT_HANDOFF.md](DEVELOPMENT_HANDOFF.md) と [PROJECT_STATE.json](PROJECT_STATE.json) を確認してください。

| 対象 | 正本 |
|---|---|
| コード・変更履歴 | このリポジトリのmain |
| 現在のデータ・モデル・未解決課題 | [PROJECT_STATE.json](PROJECT_STATE.json) |
| 最新の実測検証 | [統合データ深掘り監査](keiba_v48/DEEP_RESEARCH_RESULTS.md) |
| 採用判断 | [深掘り監査後の判定](keiba_v48/reports/deep_audit/adoption_review.json) |
| 保存成果物の一覧 | [成果物台帳](keiba_v48/reports/integration/artifact_registry.json) |
| 旧上位3着モデル・馬券精算 | [診断専用コード](research/legacy_20261007/INTEGRATION.md) |

2026-10-20深掘り監査時点：DB version 8、利用可能10,056レース、除外309レース。クラス解析など6課題を修正しましたが、同一345レースでのクラス修復後候補の回収率は49.39%（修復前候補78.29%、元の旧モデル72.29%）へ悪化しました。新候補は不採用、稼働重みと購入生成無効を維持しています。各段階の結果は原本・重み・予測ハッシュとともに保存しています。

リポジトリ直下の `jra_2023_2025.sqlite` は初期取り込み用の小さな過去ファイルです。最新の26万KB級の修復DBではありません。名前が同じでも正本として使わず、台帳の保存ID・版・SHA256を照合してください。

```bash
python -m pip install -r requirements.txt
python scripts/project_status.py
python -m unittest discover -s keiba_v48 -v
```

統合状態の整合性検査に加え、DBを手元に取得した場合は `python scripts/project_status.py --db /absolute/path/jra_2023_2025.sqlite` でSHA256とSQLiteの整合性も検査できます。

この統合はコード・保存成果物・タスク参照の一本化です。チャットのメッセージそのものを移動・結合する操作は行っていません。会話横断検索は失敗したため、未保存の会話内だけの変更まで確認できたとは扱いません。
