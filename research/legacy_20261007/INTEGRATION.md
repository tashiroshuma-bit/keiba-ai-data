# 旧診断モデルと馬券計算の統合

2026-10-07の保存パッケージ2件からコード・元README・診断JSON・精算例を取り込んだ。`ticket_math.py` とテストは両パッケージで同一であり、version 2の単独馬券パッケージを正本とした。現行モデル、ID連携、研究分割を置き換えるものではない。

- 混合モデルは馬名＋推定生年の暫定キーを使い、騎手約94%欠損。現在の公式ID方針へ流用しない。
- 上位3着分布は `historical_diagnostic_only`。重賞28例、2歳重賞4例の制約があり、独立校正済みの実勝率・購入EVと扱わない。
- 元READMEの発走前オッズ条件は当時のforecast計算の仕様。現行の回顧検証はユーザー指定の結果オッズ基準。発走前特徴への確定オッズ混入は引き続き禁止。
- 全データ・元ZIPは成果物台帳に登録済み。再学習に必要な `source_packages/`、CSV、archive.json は元の診断ZIPから取得する。データを同梱したふりはしない。
- 旧候補、データ、使用期間は研究資料として維持し、現行サービスへの自動ロードは行わない。

```bash
python -m pip install -r research/requirements.txt
cd research/legacy_20261007
python -m unittest -v test_joint_top3_model.py test_ticket_math.py
python ticket_math.py settle --plan examples/kyoto_20261004_plan.json --result examples/kyoto_20261004_result.json
```

精算例は当時の仮想購入案の計算確認であり、前向き性能の追加検証には数えない。
