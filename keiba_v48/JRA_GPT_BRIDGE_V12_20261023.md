# GPT取得経路とJRAモデルの接続（v12、2026-10-23）

ユーザーの指摘を受けて、通常Pythonの requests 直接接続とChatGPTのWeb取得経路を分離した。ChatGPT WebからJRA公式開催日程ページを閲覧できたが、出馬表の全頭原本・HTTP200応答ヘッダ・発走前観測時刻を取得したわけではない。Python環境のDNS失敗はGPT形式への変換だけでは解消しない。

**GPT用ブリッジ** `jra_gpt_bridge_v12.py`：取得済みの生HTMLバイト列＋実HTTP取得メタデータが揃う場合だけ既存v11 `build_card → capture → freeze` に接続する。GPTのレンダリング済みページテキストだけの場合は `eligible_for_preoff_freeze=false` とし、HTTP200・時刻・原本ハッシュを創作しない。4件のテスト成功。ZIP `jra_gpt_bridge_v12_20261023.zip` SHA256 `25436e4012bbdb5d34f83e55318df6bd5f85da5b8dfe56855e6491281be3a309`。

残課題：JRA出馬表の実原本を、元バイト列と取得時刻を返せる適切なツール/接続経路で取得し、レイアウトの全頭一致を検証する。検索スニペットやページ抽出テキストは正本原本として扱わない。未見の将来予測凍結0件、研究標準v7維持、本番昇格なし。