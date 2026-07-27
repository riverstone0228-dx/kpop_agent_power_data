# 無料データソース・API一覧 (2026年7月調査)

K-popアーティスト/事務所パワー計測に使うデータソース。

## 採用ソース (現行)

| ソース | 用途 | 認証 |
|---|---|---|
| **YouTube Data API v3** | 登録者・総再生・動画数 (日次) | APIキー |
| **Wikipedia Pageviews API** | 日英記事PV (日次) | 不要 |
| **Apple Music RSS** | jp/kr/us チャート (日次) | 不要 |
| **LINE MUSIC** | K-Pop Top 50 (日次) | 不要 |
| **スペースシャワーTV** | KOREAN HITS (週次) | 不要 |

### YouTube Data API v3
- 無料枠: **1日10,000ユニット**。`channels.list` は1ユニット、`search` は100ユニット
- チャンネルIDをマスタに固定し、searchを避ける運用が基本

### Wikipedia Pageviews API
- 認証不要。日本語版・英語版を分けて国内外の注目度比較

### Apple / LINE / スペースシャワー
- いずれも認証不要のJSON。詳細は [chart-sources-review.md](chart-sources-review.md) / [data-model.md](data-model.md)

## 使わないもの

### Spotify Web API — ✕ 不使用
- 2026年2月のAPI変更により必要な指標が取得不可。詳細は [spotify-api-change-2026.md](spotify-api-change-2026.md)

### Melon / レコチョク / X / Instagram
- Melon: robots.txt拒否。レコチョク: 後回し。X/IG: 自動取得不可または有料

### Google Trends — ○ 将来の補助
- v1では対象外。週次バッチとして後から追加可

## 設計方針

- 主力は **YouTube + Wikipedia + Apple + LINE + Space Shower**
- 日次取得を早く始めるほど時系列が資産になる
- 取得は GitHub Actions → リポジトリの `data/` にCSVコミット。Databricks連携はPhase 4

## 出典

- [YouTube API quota](https://developers.google.com/youtube/v3/determine_quota_cost)
- [Databricks Free Edition](https://docs.databricks.com/aws/en/getting-started/free-edition-limitations)
