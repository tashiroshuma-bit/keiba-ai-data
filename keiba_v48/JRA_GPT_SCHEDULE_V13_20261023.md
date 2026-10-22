# JRA GPT取得経路 v13：公式開催予定72レースの構造化（2026-10-23）

JRA公式の10月24日・25日の事前競馬番組（東京・京都・新潟、各12レース×2日）をChatGPT Web経路で閲覧し、予定競走名・条件・発走時刻を手動転記、全72レースをCSVへ構造化した。元ページは https://www.jra.go.jp/keiba/calendar2026/2026/10/1024.html および https://www.jra.go.jp/keiba/calendar2026/2026/10/1025.html 。**開催予定であり確定出馬表ではない**。出馬投票・天候等で変更される可能性がある。

`jra_gpt_schedule_bridge_v13.py` は公式開催日程URL・日付・全36レース/日・各場1～12R・重複・発走時刻・観測記録を検査し、`prediction_eligible=false` と `official_original_http_verified=false` を保持する。7件の単体テスト成功。実装と72レースCSV/JSONはローカルZIP `jra_gpt_schedule_v13_20261023.zip`（SHA256 `37f569126b28b1fa4efb7547259d13c9816242a498bd7bdbc83a53699616be8c`）に収録。GitHubには検証記録のみ保存し、ZIP自体は未登録。

Pythonから `www.jra.go.jp`/`jra.jp` のHTTP取得を再試行したがDNS名前解決失敗。Web経路の表示テキストは原本HTTPレスポンスではなく、観測時刻は記録作成時刻、SHA256は転記テキストに対する値。**実出馬表全頭原本取得0件、将来予測凍結0件**。v11の原本証拠ゲートは緩めない。v7研究標準維持・本番昇格なし。次は公式実出馬表の馬番・馬名・騎手・負担重量・頭数・発走時刻と原本バイト列の取得・検証。