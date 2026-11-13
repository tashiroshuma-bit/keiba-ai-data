# V51の統計手法を全面改修：階層化・非線形・時系列 Joint Top3 Plackett–Luce 研究版

**状態：研究用統計モデル実装／GitHub CIによるユニットテスト。正本v12全レースでの新方式の再学習と精度向上実測は未実行。正式V51は無変更。**

## なぜ係数倍率の調整から転換するか

実正本2023〜2026年の31+14特徴量研究（PR #33、`reports/v51_14_real_train_rank_metrics_20261113.json`）では、2025後期594Rの1着的中数が149→157となりLog Loss/Brier/ECEも改善した一方、開催日ブロック95% CIが0を跨いだため正式採用は不可。2026事後監査でも順不同3頭が145→142と悪化した。現方式の第1着だけの残差調整には限界がある。

### 今回の構造変更（単なる係数倍率ではない）

1. **1〜3着の順位を同時推定**：各レースで残りの馬から順に着順を選ぶ3段階条件付きPlackett–Luce（PL）の**加重負対数尤度を同時最小化**する。単独の勝者回帰＋別々の順位係数を廃止する研究案。
2. **階層型部分プーリング**：3着順ヘッドは独立しつつ `coupling/2 × (||w2−w1||²+||w3−w1||²)` で係数を共有し、少数の3連単的中ラベルへの過適合を抑制。
3. **非線形特徴量**：現行31＋新14のレース前利用可能な指標から、閾値付き区分線形スプライン14個、交互作用12個を生成。合計71次元。**標準化の平均/標準偏差は2023〜24年の学習期間だけから学習**。
4. **時間減衰を伴う重み付き最尤**：過去実績への半減期365日・730日・減衰なしを候補として比較。古いデータを恣意的に削除せず、十分なサンプルを維持。
5. **適切な確率評価と時系列区分**：2025年前期1145Rで1・2・3着条件付き確率を校正、中期1186Rで**Log Lossの加重和（1着50%、2着30%、3着20%）**により7つの先決候補から選択。後期594Rは選択に使わず最終確認。2026年2411Rは選択後の事後監査。
6. **開催日ブロック・ペアブートストラップ**：同一レースの勝者的中、勝者LogLoss/Brier、順序3頭・順不同3頭について開催日単位の再標本化を3000回行い95%信頼区間を出す。
7. **極めて保守的な本番移行**：2025後期の1着的中率改善の95%CI下限>0、LogLoss改善の95%CI上限<0、Brier非悪化、順序/順不同3頭非悪化などを同時要求し、1項目でも満たさなければ正式V51は変更しない。

### 統計的な目的関数

レース `r` の第 `s` 着時点でまだ残っている馬の集合を `A(r,s)` とし、事前特徴量 `x_i` と順位別係数 `w_s` に対して

```text
P(position_s = i | earlier finishing horses removed, x) =
   exp(x_i · w_s) / sum_{j in A(r,s)} exp(x_j · w_s)

L = sum_{s=1}^{3} lambda_s * weighted_mean_r[
        -log P(actual_position_s | earlier finishers, x)]
    + ridge/2 * sum_s ||w_s||^2
    + coupling/2 * (||w_2-w_1||^2 + ||w_3-w_1||^2)

lambda = (1.0,0.7,0.5) / 2.2
```

第2/第3着の条件付き損失は順位が一意に確定しているレースのみ使用する。3頭立ての第3着は分母に1頭だけ残り条件付き確率1とみなす。

### ソース・時点制御

- 正本DB: `jra_2023_2025_v12_horse_ids_full_20261111.sqlite` SHA256 `5d16777588420ac88bab5df21defb85d9346c2b918bb71859af06893752bcadd`。
- レビューDB: `jra_review_1975_verified_v2_20261111.sqlite` SHA256 `5f80b199b61b401fb046a0d7c2fb065b8c433dbc5734fcbefb5f0740ae3d03ea`。
- 過去レース結果由来の新14特徴量は2暦日以上前の履歴からのみ作成。当日結果・当日最終オッズ・当該レース結果PDFの馬体重を当該予測に流用しない。
- **制約**：旧31特徴量の歴史的出典公開時刻と当時の取得ログは全件実証できていない。年度別結果PDFの翌日公開は初回公開時刻の証明ではない。このため後期2025年検証は回顧検証であり、真正の未来凍結予測と同義ではない。
- 正本の162392頭分をGitHubに公開することはしない。既存正式V51のモデル係数・標準予測ポリシーは維持。

## 追加コード

- `scripts/v51_joint_pl_new_statistics.py`：階層Joint PLの同時最尤、71次元の非線形デザイン、レース日を使った重み付け。
- `scripts/v51_joint_pl_real_2025_study.py`：正本から特徴量生成、実日付でのデータ分割、7候補、確率校正、対照比較、2026事後監査、95%CI、研究用JSON成果物。
- `tests/test_v51_joint_pl_new_statistics.py`：PL順位条件付け・3頭立て・非線形変換の学習/検証分離・時間減衰・不正データ遮断を検査。
- `tests/test_v51_joint_pl_real_2025_study.py`：順位の適切な対数スコアによる候補選定と開催日単位の統計的比較を検査。

## 正本があるPython実行環境での再現

```bash
python -m scripts.v51_joint_pl_real_2025_study \
  --database /data/jra_2023_2025_v12_horse_ids_full_20261111.sqlite \
  --review-overlay /data/jra_review_1975_verified_v2_20261111.sqlite \
  --historical-feature-script scripts/jra_historical_horse_id_ablation.py \
  --model operations/prediction_policy/standard_v51_model.json \
  --output-dir /data/v51_joint_pl_2025_comparison_20261114
```

正本のSHAが異なる場合には、比較を実行せずエラー終了。正常終了した場合だけ `v51_joint_pl_real_statistical_comparison.json` と `v51_joint_pl_research_candidate.json` を生成する。**`production_enabled=false` を必ず維持。**

### 実行可否と限界（2026-11-14）

GitHub Actionsには正本362MBが保存されておらず、会話のコンテナ/Python実行は `ClientError` で利用できない。そのため、この変更のコード・数学的一貫性・合成テストは評価できるが、**新Joint PL方式の2025年・2026年実レースの成績は今は算出していない**。過去PR #33の25.08→26.43%をこの新しいモデルの実績として転載・混同することは禁止。

### 調査した外部一次資料

- 2026年の順位統計研究: [Statistical ranking with dynamic covariates, JRSS B](https://doi.org/10.1093/jrsssb/qkaf048)（比較ごとに変化する共変量とPLモデル）。
- 確率予測の評価指標: [Proper Scoring Rules for Estimation and Forecast Evaluation (2026)](https://doi.org/10.1146/annurev-statistics-042424-050626)。
- 校正と評価データ分離: [scikit-learn CalibratedClassifierCV documentation](https://scikit-learn.org/stable/modules/generated/sklearn.calibration.CalibratedClassifierCV.html)。温度校正はトップ選択順位を変えないため、順位精度とは分離して評価。
- [Leakage-aware race-level upset-risk diagnostics (2026)](https://doi.org/10.3389/frai.2026.1922250)（レース別時系列分離、Brier/Log Loss、信頼区間）。
