# V51 新14特徴量の正本全期間再学習・2025年順位比較：実行監査（2026-11-11）

## 実行上の判定：正本DBの全期間再学習は**未完了**

今回の対話中に以下の正本ファイルを Library `/競馬` から実体化したが、ローカルPython/コンテナが繰り返し `ClientError` となり、SQLiteを開いて実学習を完走できなかった。したがって「新しい14特徴量で的中率が上昇した」「最良係数を得た」等の数値は**一切報告していない**。

- `jra_2023_2025_v12_horse_ids_full_20261111.sqlite`、ファイルサイズ **362,139,648 bytes**、以前に検証済みのSHA256 `5d16777588420ac88bab5df21defb85d9346c2b918bb71859af06893752bcadd`。今回のツールではSHA256再実行ができなかった。
- `jra_review_1975_verified_v2_20261111.sqlite`、サイズ **6,254,592 bytes**、既存監査SHA256 `5f80b199b61b401fb046a0d7c2fb065b8c433dbc5734fcbefb5f0740ae3d03ea`。今回のツールではSHA256再実行ができなかった。
- 取得成功したファイル実体化パスは `/mnt/data/files/jra_2023_2025_v12_horse_ids_full_20261111_2.sqlite` と `/mnt/data/files/jra_review_1975_verified_v2_20261111_2.sqlite`。当該環境限定の作業パスであり、GitHub Actions上には**存在しない**。
- GitHub Actionsは通常のCIでしかなく、ユーザーLibrary内の362MB正本を自動参照できない。**合成ユニットテストの成功を実データ再学習と呼ばない**。

## 正しい既存V51比較基準

Source: `reports/v51_recovered_ids_cal2025_heldout2026.json` / `reports/v51_real_2025_2026_rank_ablation_full_20261111.json`。

| 実着順と照合したコホート | 現行V51の1着指名的中数 | 率 | 新14特徴量の実測結果 |
|---|---:|---:|---|
| 2025年全期2,925R | 719 | 24.58% | **未算出** |
| 2025年後期594R（真の最終確認区間） | 149 | 25.08% | **未算出** |
| 2026年既存固定監査2,411R | 603 | 25.01% | **未算出** |

2025年は前期1,145R（確率校正）、中期1,186R（候補選択）、後期594R（採否判定）の開催日分割を再利用。2026年は以前に分析済みの後年固定監査であり、選択には使わない。いずれも過去のJRA公開時刻の全証明を伴う真の前向き実験ではない。

## 追加14特徴量・再学習パイプラインの実装済み変更

- `scripts/v51_four_axis_historical_features.py`：クラス/相手関係、過去4角/脚質、条件別騎手、**前走までの**馬体重を、レースIDと馬番で結合した14特徴量と明示的欠損フラグで生成。前年・同年の**過去2暦日以上**の結果に限定し、評価レース自身の着順や体重を新特徴量へ使用しない。
- `tests/test_v51_fouraxis_canonical_sqlite_integration.py`：本番正本に近い構造のSQLiteを用意して、3レース9出走行からクラス・4角・前走体重・騎手を再現、前日結果の逆流を遮断。**合成データなので有効性実測ではない。**
- `scripts/v51_four_axis_rank_residual_study.py`：元の正式V51の31特徴量とステージ係数を固定し、14特徴量に対する第1着スコア加算部分だけ2023～2024年の実履歴で再学習。4特徴群（クラス/相手、脚質、騎手、前走体重）と組合せ、Ridge 0.03/0.10を比較。2025中期のみで候補選定、2025後期の開催日ブロック・ペアブートストラップ下限>0＋Log Loss/Brier/ECEの改善・非悪化で採否判定。
- `scripts/v51_four_axis_rank_residual_study.py` から、2025全期と**評価専用の2026**に対し、1着的中率、Log Loss、Brier、ECE、順序3頭完全一致と順不同3頭完全一致を出力する。採用ゲート不合格でも、候補と現行V51の比較値を保存し、係数正式採用の候補にはしない。年別の各特徴量実観測件数も出す。
- `scripts/v51_fouraxis_complete_real_run.py`：正本2ファイルのSHA256・バイト数・SQLite `quick_check` を先に検査し、全実レースの入力取得率監査と研究用再学習・2025順位比較を**1本のコマンドで実行**。失敗時は完走を装う領収書を作らずエラー終了する。出力を新規フォルダに保存し、正式V51は更新しない。
- `tests/test_v51_fouraxis_fullscore_integrity.py`、`tests/test_v51_fouraxis_complete_real_run.py`：順位完全一致の分母とソース誤認防止、実正本不在のフェイルクローズを検査。**テストの回帰結果は実2025年の成績ではない。**

## 正本実データの1コマンド実行

このコマンドは**DBのある実行環境でのみ**成功する（GitHub Actionsの空のランナーでは起動しない）。

```bash
python -m scripts.v51_fouraxis_complete_real_run \
  --database /data/jra_2023_2025_v12_horse_ids_full_20261111.sqlite \
  --review-overlay /data/jra_review_1975_verified_v2_20261111.sqlite \
  --historical-feature-script scripts/jra_historical_horse_id_ablation.py \
  --model operations/prediction_policy/standard_v51_model.json \
  --output-dir /data/v51_fouraxis_2025_fullrun
```

正常完了した場合だけ次を出力：

- `v51_four_axis_source_coverage.json`（正本DBの全件フィールド充足率）
- `v51_four_axis_2025_rank_research_report.json`（候補選択・2025後期検証・2025全期参考・2026固定監査・各特徴の年別カバレッジ・95%CI・採否）
- `v51_four_axis_2025_research_proposal.json`（正式採用禁止 `production_enabled=false` の係数）
- `v51_four_axis_2025_rank_summary.md`（一目で比較できる日本語表）
- `v51_four_axis_run_receipt.json`（実DB・SHA・実行成功の監査記録）

## 結論
2025年の新14特徴量モデルの改善率は**現時点では計算不可能**。入力は実体化済みだが、実行側の `ClientError` が阻害している。次に実行するべき処理を単一化し、正本全件の学習が可能となるまで正式V51のモデル係数やバージョンは据え置く。新たな課金・JRA-VAN/Colab利用・個人データの公開共有は実施していない。
