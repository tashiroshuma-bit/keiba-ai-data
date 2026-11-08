# JRA正本DBの4サイト連携・監査・実装結果（2026-11-08）

## 完了状態
**JRA正本SQLite v11そのものは上書きしていない。** 過去検査でLibrary再取得したコピーのサイズが不足しており、再取得完全性が確認できないため、先にJRA公式結果と4サイトのソース情報を格納する独立した補助SQLiteを作成し、GitHub mainへ実際に保存した。

### 作成して検証したSQLite
- `operations/data_updates/multisource_overlay_20261108.sqlite`
- 実ファイル：69,632 bytes
- SHA256：`54785edcd0927fa0038e3686cf9ee1da423a70114ef8a91f35ca36822537197d`
- GitHub Actionsが保存直後に **別の接続で再読込** し、`PRAGMA integrity_check=ok`、`foreign_key_check` 違反なし、保存SHA一致を確認。
- プロバイダ：5件（JRA公式、netkeiba、JRA-VAN NEXT、馬ランド、スマート出馬表）
- JRA公式結果の監査インデックス：**2026-11-08の36レース**
- 他サイトの出馬表情報と公式結果の不一致を隔離：**1件**（東京1R。JRA結果11頭 vs netkeiba出馬表の閲覧結果10頭。公開タイミング、出走取消などの可能性があり、サイトの誤りとは断定しない）
- 他サイトから持続的に保存した競走馬単位の予測特徴量：**0件**。利用規約・取得権限・正確な発走前日時の未確認データは一切インポートしない。

## データソースごとの取り込み方針

|取得元|対象項目|現在の利用条件・採用判断|
|---|---|---|
|JRA公式|成績・結果・照合用主キー|最優先の正本。公式馬IDと結果は原文証拠で検証|
|netkeiba|出馬表・馬の過去成績・直前オッズ・血統|無料と有料の区別。大量の自動取得は通信制限・規約確認が必要。公式結果と不一致なら隔離|
|JRA-VAN NEXT|40年以上の過去成績、騎手、血統、調教|月額880円の契約商品。契約・再利用許可を推測しない。無償契約なしでは公式全データを取り込めない|
|馬ランド|重賞のコース傾向、血統、坂路調教|公開の分析情報を参照。保存・二次利用は権利確認後。現時点でサイト応答429も観測|
|スマート出馬表|父系・母父系、テン・上がり、脚質、コース適性|v3は公開、v4には期限付き公開・会員向けの機能がある。継続的な大量抽出は未許可|

**参照サイト**：
- https://rsp.netkeiba.com/info/kiyaku.html
- https://support.keiba.netkeiba.com/hc/ja/articles/39720493823129-データベースの閲覧ができない-通信制限がかかった-スクレイピングについて
- https://jravan.jp/nx/hdata.html
- https://jravan.jp/buy/
- https://www.umarand.com/
- https://www.smartrc.jp/v3/
- https://www.keiba-salon.com/20260105_76656/

## 今回実装したDB取り込み処理

### 1. 複数データソースの登録と特徴量保存
`scripts/enrich_v11_multisource.py`
- 既存正本のバックアップコピーにだけ、新しい`multi_source_registry`、`multi_source_observation`、`multi_source_import_audit`を作成。
- 血統、騎手・調教師、近走タイム、脚質、相手能力、坂路調教、馬体重、馬場、発走前/確定オッズなどの22項目を受け付ける。
- すべての項目にソースURL、取得元、SHA256、観測時刻、可能な場合は公開時刻、使用権限・根拠を保持。
- JRA公式馬IDは**同レース・同馬番・正式プロフィール証拠**を必須とし、馬名の類似による強制ID紐付けを禁止。
- 発走前の実測オッズは、タイムスタンプと全頭の市場スナップショットを満たす場合だけ研究用入力として検査。
- 入力は権限済みJSONLファイルのみ。クローラー・JRA-VANの契約回避・情報の無断配布を実装しない。
- v11原本のSHAと履歴表の件数を検査し、ソースDBに直接書き込まず出力用DBだけに変更する。独立の整合性検査を通す必要がある。

### 2. 発走前に使える情報だけの出力
`scripts/query_multisource_preoff_features.py`
- 各馬の公式ID、公開日時、観測日時、予測日時と発走日時が完全に一致する情報のみ取り出す。
- 単勝オッズは**同一ソース・同一時点で全馬分**揃わなければ使用しない。
- 後出しの最終オッズ、3着以内の結果、予測時刻以降に初出したデータは用いない。
- 正式v50の予想順位・確率・買い目は変更しない。

### 3. ソース同士の矛盾を隔離
`scripts/audit_jra_multisource_race_card_conflicts.py`
- 東京1Rのnetkeiba出馬表「10頭」とJRA公式結果「11頭」の表示差を発見し、`QUARANTINE_FIELD_CONFLICT`として保存。
- 記録時刻の違いや取消・除外など原因の詳細は確定していない。自動統合・結果修正は行わない。

### 4. テスト
- 5サイト別の権限、正式ID、時系列切断、欠測、出力DB保存、元データ不変をテスト。
- 全頭未取得オッズは入力不可、過去公開時刻が欠ければ研究用予測の特徴量にならないことをテスト。
- GitHub Actionsの `test_jra_multisource_ingestion.yml` 成功。
- `audit_jra_multisource_cards.yml` 成功。
- `build_jra_multisource_overlay.yml` 成功、保存したSQLiteを再読込して検証。

## v11本体の完全性に関する未解決問題
GitHub管理データの読取問題とは別に、前回正本v11のLibraryから取り出した**最初のコンテナコピー**はサイズ299,909,120 bytes、SHA256 `d878001b4b2fa80f2479c10584ba27cbd562d2235a0aee1479a1f50440163af6` で、期待322,170,880 bytes、SHA256 `7206c787e6b13616e0ac1a0950d31a2539188c466fd369bdcd916f4f58f59627`と不一致、SQLiteとして不正だった。元の作業用v11原本は正常であり、この事実だけでLibrary保管ファイル自体の破損とは断定できない。2回目のmaterialize呼出しはファイルサイズ報告のみ取得でき、実体検査はツール障害で未完了。

このため**今回、Libraryの大容量正本ファイルは上書きせずv11を維持**。新しい補助DBを別途保存し、大容量ファイルの整合性が再確認できるようになるまではv12として正式宣言しない。

## 本番切替
- `PROJECT_STATE.standard_forecast` は引き続き **v50**。
- `PROJECT_STATE.database.version` は引き続き **11**。
- 今回のユーザー依頼に対する実装成果は正本と別ファイルの検証済みSQLite、取込プログラム、時点検証・照合システム。
- 新しいライセンス付き4サイトの過去出走馬全件データを既に格納したという主張はしない。

## 残る入力条件
1. 新たな提供元ごとに適切な利用権限を取得し、再利用可能な構造化エクスポートか事実観測記録を保存する。
2. 発走前公開・取得時刻が検証できる完全な出馬表・レース別オッズ・公式馬IDを継続的に保存する。
3. 正本v11完全コピーを取得し、SHA256・PRAGMA・履歴件数を検証してから、新たな提供元情報をv12候補DBへ移行する。
4. v50との同条件・同レース検証を経た特徴量だけを順位モデルの改修候補へ進める。

## 実装・検証ファイル
- `operations/data_updates/multisource_overlay_20261108.sqlite`
- `operations/data_updates/multisource_overlay_20261108_audit.json`
- `operations/data_updates/five_source_access_and_rights_registry_20261108.json`
- `scripts/enrich_v11_multisource.py`
- `scripts/query_multisource_preoff_features.py`
- `reports/v51/multisource_race_conflict_audit_20261108.md`
- `operations/data_updates/canonical_db_v11_materialization_exception_20261108.json`
