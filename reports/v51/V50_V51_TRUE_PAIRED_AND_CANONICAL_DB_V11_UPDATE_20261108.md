# v50→v51正式比較準備・正本DB v11更新結果（2026-11-08）

## 結論
- **正本DBアップロード・Library上書き・独立再ダウンロード照合まで完了**。ファイル `/jra_2023_2025.sqlite`、Library安定ID `libfile_c859130783008191865589ca48bc3c6f`、version_id `11`。サイズ 322,170,880 bytes、SHA256 `7206c787e6b13616e0ac1a0950d31a2539188c466fd369bdcd916f4f58f59627`。SQLite `PRAGMA integrity_check=ok`、外部キー検査正常。旧DB SHA256 `5a7dcd864286ccb60a43dd644a0fbe050ea25425e7e39effa7fa70fdc3128ebc`。
- v11追加：`jra_20261108_official_podium_supplement` にJRA公式結果11月8日の36R×上位3頭=108行を追加。既存 `annual_report_races` 13,176R・`annual_report_runners` 181,345行は不変。障害2Rは別フラグ。新テーブル `preoff_eligible=0`。**完全な全馬走歴の追加ではない**。
- V50 vs V51同一レース・同一日時・公式馬IDの正本比較：**適格ペア0R**。11/8のv50系A–D保存研究予測36Rは存在するが、同じ時刻で公式馬ID・発走前履歴の初出を証明したV51全頭予測スナップショットは0R。したがって正式V51の精度改善は実証できていない。
- **正式標準はv50を維持**。実データで検証した研究V51は2025年に1着・Top3指標が悪化し、2026年もTop3・LogLoss悪化。係数を本番へ切り替えない。

## 公式馬IDの再照合と証拠
- 既存 `annual_report_runners.horse_id IS NULL` 77,317行。
- 同じレースID・馬番・馬名による `official_identity_evidence` の未リンク確定可能行 **0**。競走馬名のみで遡ってIDを推測しない。
- 2026年11月8日のJRA公式レース結果ページ36件から新しいプロフィールIDリンクを収集する独立処理を実行したが、取得した現在のHTMLでは出走馬のプロフィールIDを抽出できず、36件とも `official_id_unavailable`（0馬）。失敗理由は `operations/results/2026-11-08/jra_official_runner_identity_evidence.json` に保存。閲覧できたサイトのトップナビゲーションだけを身元証拠とはみなさない。
- 現状、公式証拠で新たに確定した馬IDは **0**。未連携ID77,317行は変更なし。

## 発走前の情報証明
- `annual_time_evidence` は13,176Rの結果を保存しているが、正式な `result_published_at` が確認できた行は0。後日観測日時を歴史的な初回公開日時にすり替えない。
- 新規 `jra_model_pair_replay_evidence` は将来の発走前取得SHA、公式ID・公開時刻の検証、モデルペア可否のスキーマ。空の状態で作成しており、証拠のない仮ペアは生成しない。

## V50/V51比較を実行できる経路
- `scripts/standard_v50_forecast.py` に任意の `--v51-research-features` を追加。
- 完全な全馬データ、モデル入力日時、発走日時、公式馬ID・プロフィール証拠、当時公開済みの過去情報が一致する場合のみ、**同一レース・同一発走前asof**でV51研究順位を付記。入力不足ならエラーで中止し、v50の順位・確率・買い目は不変。
- `scripts/evaluate_v50_v51_true_paired.py` が、公式結果と凍結したv50/v51両方の予測を完全照合する。1着指名、勝馬上位3捕捉、LogLoss、Brier、接戦・多頭数条件別比較、ペア不一致のexact検定、日付クラスタBootstrapを実装。ソース未充足時は `NO_ELIGIBLE_PAIRS` を返し、偽の的中率を作らない。
- 2026-11-08の保存研究予測に対する実行結果は **0/36適格**（候補v51は学習済み重みしかなく、当時凍結した出走馬別の予測値を保存していない）。

## 運用切替の厳格ゲート
1. 馬番・馬名・公式馬IDが完全一致し、発走前情報の公開時刻・観測時刻が記録されたV50およびV51予測を同時凍結する。
2. 公式結果は発走後に別途保存する。予測後のオッズ/出走情報を遡及利用しない。
3. 同一100R以上を目安に、勝馬1着指名・上位3捕捉・LogLoss・Brierが劣化せず、日付クラスタ95%区間・符号検定で改善根拠を確認する。単発大波乱を理由に通常レースへ穴馬加点しない。
4. 未完成の馬ID連携や完全公開時刻を未確認のまま「検証済み」と呼ばない。

## GitHubソース
- `operations/data_updates/canonical_db_v11_update_verified.json`
- `PROJECT_STATE.json` : `database.version=11` / `standard_forecast.version=v50`
- `scripts/standard_v50_forecast.py`
- `scripts/v51_candidate_race_overlay.py`
- `scripts/evaluate_v50_v51_true_paired.py`
- `reports/v51/v50_v51_paired_verification_status.json`
- `operations/results/2026-11-08/jra_official_runner_identity_evidence.json`
- `operations/results/2026-11-08/v50_abcd_settlement.json`
