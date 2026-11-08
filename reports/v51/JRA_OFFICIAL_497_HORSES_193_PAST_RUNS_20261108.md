# V51向けJRA公式実データ投入・時点検証（2026-11-08）

## 実施と検査結果
JRA公式デスクトップの**レース結果**と**競走馬プロフィール**を利用し、馬番・馬名・10桁公式馬IDを正確に結合して、今後の出走前モデルに使える過去走補助データを新規構築した。追加課金、JRA-VAN NEXT契約回避、netkeiba等の無断大量抽出は行っていない。

|証拠ソース|実投入件数|検証|
|---|---:|---|
|JRA公式 2026年11月8日全場全レース結果|36/36R|公式着順・人気・馬番・プロフィールID照合|
|同日レースの公式馬ID付き全馬結果|497行|保存・SHA256・SQLite integrity/foreign key再読込成功|
|京都12R 公式競走馬プロフィール|18/18頭|プロフィールと結果表の公式ID一致|
|同18頭の2026年11月8日より前の成績|193行|レース日・競馬場・距離・馬場・人気・着順・騎手・体重・タイム保存|
|その他4サイト（netkeiba/JRA-VAN/馬ランド/スマート出馬表）の新規馬別観測|**0行**|権限/取得時刻不明のデータを虚偽投入せず|
|V50・V51同時凍結の適格レース|**0R**|直前の予測同時比較は依然不可|

### JRA公式全馬結果（v2・36R）
- `operations/data_updates/jra_official_20261108_all_runner_history_v2.sqlite`
- SHA256 `4912237e688804cdbaed6a4d0b9a2019fd126b309c938fb21d8c1a637397959b`
- 290,816 bytes。36レース・497頭。福島4Rは11出走頭のうち2頭の未完走を`finish_position=NULL`として保持し、以前の9頭着順集計と正しく区別した。
- 全馬の公式プロフィールリンクはJRA結果ページ自身に存在する`/JRADB/accessU.html?CNAME=pw01dud00（10桁ID）/...`から取得。馬名の類似による推測ID結合をしない。
- `operations/data_updates/jra_official_20261108_all_runner_history_v2_audit.json` にレース単位の証拠と再読込結果。

### 京都12R 18頭の過去成績補助データ
- `operations/data_updates/jra_official_20261108_kyoto12_horse_profiles_v1.sqlite`
- SHA256 `1558a0ac7dbaebf8edd751f586ea7c5cab19e23c814374028cdf34487754a39f`
- 94,208 bytes、18頭の公式プロフィールに対する**過去成績193行**。JRA公式プロフィールを低頻度で取得。
- 2026年11月8日以降のレース結果は過去走表から除外。元の11月8日予測へ後付け使用していない。
- `operations/data_updates/jra_official_20261108_kyoto12_horse_profiles_v1_audit.json`で18件成功、0件失敗、過去走193行とSQLite検査成功を証明。

## 発走前情報・時点監査
これらのJRAサイトの情報は、**2026年11月8日の結果が終わった後に実際に確認したもの**。過去の結果の正確な初回公開時刻は証明できていない。
- 11月8日のV50/V51を再計算するときにこの情報を利用してはいけない。
- 今後のレースは、取得・保存した`observed_at`より後に発走前予測を実施し、過去走のレース日が対象日から少なくとも2暦日以前であれば、**その時点で実在した履歴**として利用可能。
- ただし「11月8日より前の予測で利用可能だった」との遡及主張は厳禁。

検証済み読み出しコード：
- `scripts/query_jra_official_past_runs_asof.py`：公式IDで同日の全馬結果から次開催の過去走実績を読み出す。
- `scripts/query_jra_official_profile_form_asof.py`：公式IDで18馬の過去結果から直近5走、3着以内数、芝/ダート出走数などの研究用特徴量を取得。
- 実レコードに対する自動テスト：未来からの結果混入、11月8日同日の逆流、公式ID不一致、DBバイナリ改ざん、タイムゾーン欠落を拒否。

## V51の改善判定
**現状では判定不能。** V51の予測改善を説明する新規学習行は増えたが、独立して未来予測を凍結したレースと、その後の着順結果がまだない。今回の193行は過去走の補助説明、497行は発走後の結果。モデル重みを2026年11月8日の結果に合わせて最適化しない。

- 今後の出馬表全頭に同じ精度で公式IDが付与された場合に、v50とv51の**同一レース・同一asof**予測を両方発走前保存してから結果を検証する。
- 以前の2025・2026年再学習では、V51候補が全指標で改善できず正式昇格基準未達。**PROJECT_STATE.standard_forecast.version=v50を維持**。
- メインの322MB正本DBのLibrary再取得は以前整合不良があったため、本作業で無検証の上書きをしない。新しい検証済みSQLiteは別の補助DBとして保存し、将来の正本更新時に参照。

## 出典・検証実行
- JRA公式レース結果（例）：https://www.jra.go.jp/JRADB/accessS.html?CNAME=pw01sde0108202605021220261108%2FB4
- JRA公式馬プロフィール（例）：https://www.jra.go.jp/JRADB/accessU.html?CNAME=pw01dud002021103488/F3
- 全馬結果 GitHub Actions：https://github.com/tashiroshuma-bit/keiba-ai-data/actions/runs/42476414366
- 未来参照条件テスト：https://github.com/tashiroshuma-bit/keiba-ai-data/actions/runs/42476602104
- 馬プロフィール投入：https://github.com/tashiroshuma-bit/keiba-ai-data/actions/runs/42476949131
- 馬プロフィール読み出しテスト：https://github.com/tashiroshuma-bit/keiba-ai-data/actions/runs/42477130378
