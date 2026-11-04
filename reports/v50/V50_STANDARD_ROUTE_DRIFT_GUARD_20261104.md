# 2026-11-04 v50 標準経路ドリフト拒否（研究・保守修正）

## 確認した正本
GitHub main の AGENTS.md、DEVELOPMENT_HANDOFF.md、PROJECT_STATE.json、reports/v50/V50_REAL_HISTORICAL_STATISTICAL_REPORT_20261102.md を読取。PROJECT_STATE.database は version 10 / SHA256 5a7dcd864286ccb60a43dd644a0fbe050ea25425e7e39effa7fa70fdc3128ebc、standard_forecast は v50。DB実体の再SHAは本作業では未実施。

## 実装
scripts/standard_v50_forecast.py に、予測開始前のfail-closed検査を追加。PROJECT_STATE.standard_forecast の v50、ユーザー採用フラグ、正式policyパス、正式entrypointが一致しなければ拒否。policy側もentrypoint、履歴遅延2日、騎手残差係数1、温度0.70を検査し、意図しない変更を拒否。基礎A、確率計算、正本DB、既存予測、実購入無効の設定は変更しない。研究校正T=1.25は本番へ採用しない。

## テスト
tests/test_v50_standard_policy_guard.py に2ケース追加：PROJECT_STATEのv49への誤退行と温度1.25への無断変更を、DBアクセス・出力作成前に拒否する想定。**この実行内でテスト実行結果とGitHub Actions完走を確認できていないため、合格とは記録しない。** コード・テストのGitHub保存は完了。

## 採否
保守用ガードとしてコード追加。実DBを使うE2E、全6036Rの同一条件v49-v50比較、別期間校正、将来freeze/settle、公式馬ID確定、未見再学習は未完了。v50正式標準指定は維持。実購入無効。JRA原本はGitHubへ保存していない。

## 前回までの既閲覧回顧（今回更新なし）
2026年2409R：単勝1点611/2409=25.36%（目標90%、9点2208/2409=91.66%）、馬連1点226/2409=9.38%（目標80%、34点1968/2409=81.69%）、3連複1点143/2409=5.94%（目標70%、74点1689/2409=70.11%）。勝ち馬上位3捕捉1325/2409=55.00%（目標90%）。多点捕捉は正式1点的中率でも回収率でもない。
