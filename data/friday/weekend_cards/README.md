# 金曜21時・週末JRA出走情報の取り込み（途中停止なし）

## 出力ルール
正本履歴DB（Git data/friday-three-year-history）の2023〜2025年の成績は常に別途集計。週末の出走情報は **任意入力** とし、0件でも履歴集計は止めない。

1. 外部公開情報を `scripts/friday_fetch_public_cards.mjs` が**ベストエフォート**で取得する。現状は netkeiba 公開出馬表を試みるが、アクセス拒否・未公表・HTML変更時はエラー記録のみで継続。公式JRA原本の完全照合の代替ではない。
2. 外部または手動入力のCSVを `data/friday/weekend_cards/*.csv` に保存できる（スマホからGitHubに登録可能）。試験用の架空CSVは必ず `tests/fixtures/` に分離し、本番に混入させない。
3. `scripts/friday_prepare_available_cards.mjs` が次の土日以外・不正CSV・重複や衝突を検出。矛盾する馬番・騎手は空欄とし、レース全体は止めない。
4. `scripts/friday_nonblocking_cards.sh` が出走馬名と過去の**公式馬IDを完全一致・単一候補の場合のみ照合**。騎手も公式IDの名前完全一致・単一候補の場合のみ照合。あいまい一致や名前だけの推測IDは使わない。
5. 出走馬が1頭でもあれば `reports/friday_operational/INDEX.md` と `日付_競馬場_R.md` を生成。0頭なら過去3年DBと監査用CSVを発行したまま、`HISTORICAL_ONLY` を表示する。

### 入力CSV（UTF-8、先頭行は必須）
```csv
date,venue,race_no,race_name,surface,distance_m,horse_no,horse_name,jockey_name,card_status,source_type,source_url,source_captured_utc
2026-11-22,京都,11,マイルチャンピオンシップ,芝,1600,,エンブロイダリー,C.ルメール,PROVISIONAL,USER_PROVIDED,,2026-11-16T00:00:00Z
```

上記は**入力形式の説明用**で、公式確定出走表・騎手・枠順を表すものではありません。

`source_type` は `SECONDARY_NETKEIBA` / `SECONDARY_OTHER` / `USER_PROVIDED`。そのほかは検証不能扱い。第三者サイトのURLは許可したドメインのHTTPSのみ。入力された `OFFICIAL_VERIFIED` ラベルをそのまま認めない。実際のJRA公式出走表をSHA等で独立監査した場合にのみ、将来の別処理で正式確定として採用できる。

## レポートの意味

- **過去3年**：2023～2025年に公式結果原本から確認した平地の出走数・1着数・3着以内数。2026年の一部収録分は混ぜない。
- **条件**：競馬場・芝/ダート・距離が同じときの過去実績。外内回りや当日馬場は自動で同一扱いにしない。
- `0% (0/5)`：実際に5戦して該当なし。
- `－`：公式IDは照合できるが、その条件で出走0件。
- `未照合`：公式IDが未確認、複数候補、馬名相違または出走情報が未取得。**新馬・初出走馬など過去データが本当にない場合も、この状態を正常な欠損として許容し、レポートを止めない。**
- `－`（対象期間0戦）は、公式IDを照合できた馬についてだけ表示する。2023〜2025年に実績がなくても、2026年に初出走とは断定しない。
- 初出走の確定は別途、信頼できる出走情報から明示された場合だけ行う。**過去データがない＝次走勝率0%・能力なし、とはしない**。未知の値を合成して穴埋めしない。
- 週末出走情報を1件取得してもレース登録頭数・欠場馬の網羅性は保証しない。タイトルに「部分・未確定」と明記する。

## 主要な成果物

- `reports/friday_operational/INDEX.md`：スマホ用の競馬場・レース別目次。
- `reports/friday_operational/YYYY-MM-DD_京都_11R.md` など：馬の実績・騎手/コンビ/コースの2表。
- `reports/friday_operational/cards_joined.csv`：取得できた出走馬と3年間実績の照合結果。
- `reports/friday_operational/card_coverage.csv`：出走情報を取得できたレースと暫定頭数。
- `reports/friday_operational/unmatched_card_entries.csv`：未照合馬・騎手。
- `reports/friday_operational/card_sources_status.json` と `reports/friday_card_acquisition.json`：取得失敗・除外・矛盾理由。
- `reports/friday_operational/official_2023_2025_actor_condition_stats.csv`：過去3年の確定履歴統計。

**Pythonは使用しない。V51/V52の予想モデルは変更しない。過去実績と次走勝率予測は区別する。**
