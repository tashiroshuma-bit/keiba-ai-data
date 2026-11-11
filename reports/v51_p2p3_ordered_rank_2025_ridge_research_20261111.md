# V51 2着・3着の順位精度改善: 日付分割と独立Ridge研究（2026-11-11）

## 現状・事実
正式モデルはV51。学習2023〜2024年の5,865R、2025年の校正2,925R、2026年の研究対象2,411R、正本v12 SHA256 `5d16777588420ac88bab5df21defb85d9346c2b918bb71859af06893752bcadd`。

現行V51の2026既存固定評価：
- 1着指名：603/2,411 = 25.01%
- 1〜3着順不同完全一致：6.01%
- 1〜3着順序完全一致：1.33%
- 実2着馬への条件付きLog Loss：2.2177504
- 実3着馬への条件付きLog Loss：2.1870937

**根拠**：`reports/v51_recovered_ids_cal2025_heldout2026.json`、`reports/v51_recovered_horse_id_conditional_rank_oos2026_20261111.md`。これらはV50との直接実測比較ではなく、欠測馬IDを回復したV51研究モデルの結果。

## 新しい順位モデル改善コード
`scripts/v51_2025_conditional_p2p3_ridge.py` を追加。1着ステージは固定して、2着（1着を除外）・3着（1/2着を除外）の別々のRidge値について `(0.003,0.01,0.03) x (0.003,0.01,0.03)` 計9候補と現行係数を比較。予測の全着順同時分布 `P(i,j,k)=P1(i) * P2(j|i) * P3(k|i,j)` が正規化されることを検証。

- 学習係数の再推定：2023〜2024年の実データのみ。
- 2025年：同じ開催日を異なる期間に混ぜず、先頭40%で校正、次40%で候補選択、後ろ20%で真の選択後確認。
- 2着・3着の**それぞれの**条件付きLog Lossが悪化しないことと、最終確認期間の1〜3着順序／順不同完全一致を確認。1着的中率は変更されない。
- 2026年の既存2,411Rは選択が完了した後の固定監査に限り使い、モデル候補決定・Ridge値・温度選定には使わない。
- 失敗した場合は元の2着・3着係数を保持し、改善を捏造しない。
- 研究モデルを `production_enabled=false` として保存。正式V51の本番係数・標準予測を変更しない。

## 実データによる追加検証の条件
実行するにはLibraryのv12正本（362,139,648 byte、公式署名のSHA一致確認）と研究用の評価オーバーレイ（SHA256 `5f80b199b61b401fb046a0d7c2fb065b8c433dbc5734fcbefb5f0740ae3d03ea`）をGitHubコードの実行環境に読み取り専用で配置。

```bash
python -m scripts.v51_2025_conditional_p2p3_ridge \
  --database /data/jra_2023_2025_v12_horse_ids_full_20261111.sqlite \
  --review-overlay /data/jra_review_1975_verified_v2_20261111.sqlite \
  --historical-feature-script scripts/jra_historical_horse_id_ablation.py \
  --model operations/prediction_policy/standard_v51_model.json \
  --output-dir /data/v51_p2p3_2025_rank_retrain
```

出力は `v51_2025_conditional_p2p3_ridge_report.json` と `v51_2025_conditional_p2p3_research_model.json`。**新しい9候補の2025／2026実測値は現段階で未算出**。ユニットテスト・GitHub Actions成功は実レースの数値上昇の証拠ではない。

過去レースの元PDF公開時刻が完全に証明されていないため、過去再現は事前に固定した将来レース予測と同一視しない。
