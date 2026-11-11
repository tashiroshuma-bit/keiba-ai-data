# V51 2025校正・特徴係数改善: 実装完了・実測未実行の監査記録
発行日: 2026-11-11 JST

## 実施済み
1. 正式V51維持をPROJECT_STATE.jsonと標準ポリシーで確認。main commit: deeb5781be851f355a6c8e2b731c0f76caf209d8 (PR #27)。
2. 2025実レースに対する時系列校正・係数感度: `scripts/v51_2025_coefficient_calibration_grid.py`。
3. 2023-24実レースで学習係数を再推定するwinner-stage ridge候補と4群の削除再学習: `scripts/v51_2025_winner_stage_refit_study.py`。
4. 出力は研究候補のみ。標準V51本番係数・温度・予測経路は変更していない。
5. CI run 43002202762 (push) SUCCESS; run 43002211312 (pull_request) SUCCESS。CIは合成ユニットと既存の保存済み2026検証の回帰テストであり、新たな実正本DB再学習結果ではない。

## 既存実測数値の確認

元データ: `reports/v51_recovered_ids_cal2025_heldout2026.json`。V51 restored-ID full model。

| Cohort | Calibration | Win accuracy | Log Loss | Brier | ECE |
|---|---|---:|---:|---:|---:|
| 2025 2925R | none | 719/2925 | 2.2256848977 | 0.8625185307 | 0.0388294353 |
| 2025 2925R | 2025 fit | 719/2925 | 2.2224221541 | 0.8602420485 | 0.0289318609 |
| 2026 2411R | none | 603/2411 | 2.2252542232 | 0.8621457696 | 0.0492845517 |
| 2026 2411R | 2025 fit | 603/2411 | 2.2188172510 | 0.8590552528 | 0.0276300773 |

2025は校正パラメータのインサンプル。2026は後年固定研究検証であるが、発走前時刻がすべて証明されているわけではない。この表は新規追加したリッジ係数実験の結果ではない。

## 実測未完了の範囲と具体的な理由

今回の対話内でPython/コンテナ実行が `ClientError` により失敗。正本v12約362 MBを読み取り2025校正グリッドと再最適化する計算は**完了していない**。したがって新規の優良温度・最良係数倍率・top1の改善率を主張しない。CI成功は研究コードのユニット検証であって実DBの計算実行ではない。実測結果JSON（`v51_2025_coefficient_calibration_grid.json`, `v51_2025_winner_refit_report.json`）は本タスクで生成・保存したと主張しない。

入力要求:
- Library `/競馬/jra_2023_2025_v12_horse_ids_full_20261111.sqlite` SHA256=`5d16777588420ac88bab5df21defb85d9346c2b918bb71859af06893752bcadd`。
- Library `/競馬/jra_review_1975_verified_v2_20261111.sqlite` SHA256=`5f80b199b61b401fb046a0d7c2fb065b8c433dbc5734fcbefb5f0740ae3d03ea`。
- Github `scripts/jra_historical_horse_id_ablation.py`, `operations/prediction_policy/standard_v51_model.json`。

実行環境復旧後に両プログラムを上記原本で実行し、全候補の2025日付分割・信頼区間・2026固定監査を数値付きで検証する。ユーザーの既存日次改善タスクへPR #27の2コマンドを追加済み。研究候補を正式モデルへ無検証で上書きしない。

## 馬体重
既存2026体重補助研究（`reports/v51_body_weight_validation_decision_20261109.md`）では1着率21.153%→21.029%、95%CI -0.454〜+0.211pp。正式V51に体重係数を追加するエビデンスではないので現状維持。
