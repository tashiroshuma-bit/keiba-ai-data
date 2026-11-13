# V52 本番切替・過去データ比較：実施状態と根拠（2026-11-14）

## 結論：本番切替は**未実施**、実データ学習比較も**未算出**

ユーザーより **新しい階層化 Joint Top3 Plackett–Luce（71特徴量）を「v52」として本番設定し、過去データで比較**する指示を受領。

2026-11-14 の会話内でコンテナの最小シェルコマンド `echo CONTAINER_OK; python --version` およびPythonの `print("runtime_check")` はいずれも `ClientError`。前回2026-11-13の実行成功を本日再実行の証拠として扱わない。GitHub CIは動くが、正本362MBと1975レースoverlayは非公開Library内にのみある。これらをGitHubの公開リポジトリへ無断転送しない。正本無しのGitHub合成テストだけで **「V52実データ学習済み」「V52本番切替済み」にはしない**。

## 現在の実測済み比較値（**V52ではない**）

| 同一期間 | 正式V51 | 旧・追加14特徴量を用いる1着残差研究モデル | 新Joint PL / V52 |
|---|---:|---:|---:|
| 2025年後期・1着的中 | 149/594 = 25.08% | 157/594 = 26.43% | **未算出** |
| 2025年後期・勝者Log Loss | 2.260550 | 2.239632 | **未算出** |
| 2025年後期・Brier | 0.868105 | 0.863722 | **未算出** |
| 2025年後期・順序3頭一致 | 5/594 | 5/594 | **未算出** |
| 2025年後期・順不同3頭一致 | 19/594 | 25/594 | **未算出** |
| 2026年固定事後監査・1着的中 | 603/2411 = 25.01% | 623/2411 = 25.84% | **未算出** |
| 2026年固定事後監査・順序3頭一致 | 32/2411 | 35/2411 | **未算出** |
| 2026年固定事後監査・順不同3頭一致 | 145/2411 | 142/2411 | **未算出** |

旧・追加14特徴研究モデルの2025後期1着的中率改善の開催日ペアブートストラップ95%CIは **−0.67〜+3.22 percentage points**（ゼロを含み採用未達）。旧研究モデルの係数を新Joint PL / V52と誤用しない。

根拠: `reports/v51_14_real_train_rank_metrics_20261113.json`、`reports/v51_14_real_run_receipt_20261113.json`、`reports/v51_14_real_train_2025_comparison_20261113.md`。いずれも実正本v12を用いた**旧方式の**研究測定。

## V52用に実装した切替機構

- `scripts/v52_joint_pl_live_features.py`：当日の発走前に根拠確定した31+14=45特徴量を、2023/24年だけで確定した訓練時正規化定数・14個のスプライン・12個の交互作用によって71特徴量へ変換。推論当日の標準化を**再学習しない**。
- `scripts/standard_v52_forecast.py`：**推論の本番経路候補**。 `PROJECT_STATE.standard_forecast.version=="v52"`、V52専用ポリシー・実測済み`3×71`係数・正本DB SHA・2025年校正・JRA馬ID証拠・全出走馬45入力・全4特徴群の出典URL/SHA・公開/観測時刻が揃わない場合は **エラーで停止**。V51/V50の係数に自動で戻さない。順序/順不同3頭の全組合せ確率の合計が1になることを確認。
- `scripts/v52_real_promotion_gate.py`：正本v12/overlayの各SHA、2023/24年5865R訓練、2025年1145/1186/594R区分、2026年2411R事後監査、2025後期の採用ゲート・開催日ペア95%CI、3着段階までの係数・校正・生きた発走前特徴量のテスト成功に限り、**稼働させるための候補モデル**を生成。単体のテストで本番設定を変更しない。
- `operations/prediction_policy/v52_release_request.json`：ユーザーの本番指定と実データ結果・ライブ証拠の不足を改ざんなく記録。 `STAGED_V52_NOT_PRODUCTION_WAITING_FOR_VERIFIED_REAL_FIT`。
- `tests/test_v52_release_guard.py`：学習デザインと推論変換の一致、モデル未存在でのV52起動禁止、コホート不足/偽の係数/発表時刻の逆流を棄却する合成回帰テスト。**合成テストの通過は2025年の実測結果ではない。**

## 正本を使った実測手順（同じコンピューターでのみ有効）

1. 正本`jra_2023_2025_v12_horse_ids_full_20261111.sqlite` SHA `5d16777588420ac88bab5df21defb85d9346c2b918bb71859af06893752bcadd` と検証`jra_review_1975_verified_v2_20261111.sqlite` SHA `5f80b199b61b401fb046a0d7c2fb065b8c433dbc5734fcbefb5f0740ae3d03ea` をアクセス許可のある実行環境へ配置する。
2. 以下を実行し、実測ファイル2件の作成・SHAソース照合と実データのコホート一致を検証。
3. 別途、JRAの発走前に45特徴量すべてを収集できるライブ・スナップショットとタイムスタンプを一度以上保存・再演する。本番昇格に実証が必要。
4. `scripts/v52_real_promotion_gate.py` に結果を渡して、統計受入基準と実運用データ入手可能性が確認された時だけリリースモデルを生成する。
5. 運用の `PROJECT_STATE.json` と `operations/prediction_policy/standard_v52.json` の切替は、V52の本番成果物とCIでの検査成功を確認してから行う。**2026-11-14現在は未切替**。

```bash
python -m scripts.v51_joint_pl_real_2025_study \
  --database /data/jra_2023_2025_v12_horse_ids_full_20261111.sqlite \
  --review-overlay /data/jra_review_1975_verified_v2_20261111.sqlite \
  --historical-feature-script scripts/jra_historical_horse_id_ablation.py \
  --model operations/prediction_policy/standard_v51_model.json \
  --output-dir /data/v52_joint_pl_historical_compare

python -m scripts.v52_real_promotion_gate \
  --report /data/v52_joint_pl_historical_compare/v51_joint_pl_real_statistical_comparison.json \
  --candidate /data/v52_joint_pl_historical_compare/v51_joint_pl_research_candidate.json \
  --preoff-smoke /data/v52_preoff_smoke.json \
  --out-model /data/release/standard_v52_model.json \
  --out-receipt /data/release/v52_promotion_receipt.json
```

**切替時の注意**：研究モデルは既存の `v51_joint_pl_real_2025_study.py` を改変せず、V52で研究成果を比較。対象コホートは全同一レース。2026年の事後監査は選択には用いない。参照: `reports/v51_joint_pl_new_statistical_architecture_20261114.md`。

**現在の正式運用はV51**。そのままにしておくのはユーザーのV52導入指示を拒否するためではなく、**未学習の係数を本番に適用して不正な予測確率を出す事態を避けるため**。
