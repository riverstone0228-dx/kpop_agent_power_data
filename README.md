# リバーストーン・プロジェクト

2年後にAI/DXデータアナリティクスコンサルタントとして就職または独立するため、匿名データアナリティクスインフルエンサー「リバーストーン」を育てるプロジェクト。

## ゴール

- **2年後 (2028年夏)**: AI/DXコンサルとして就職 or 独立。インフルエンサー実績をポートフォリオ化
- **3ヶ月後 (2026年10月末)**: YouTube初回公開 + X・note記事公開
- **継続**: 週5〜10時間の稼働で定期運用

## ペルソナ

| | 日本向け (第一弾) | グローバル向け (将来) |
|---|---|---|
| 名義 | リバーストーン | 別名義 (未定) |
| 設定 | 架空の50代日本人男性 | 架空の20代女性 |
| 顔 | 別プロジェクトのアバターアニメ (口パク) | 別アバター |
| 声 | 加工して低め | AI英語音声 |
| 制作 | 日本語で制作 | 日本語版をAIで英語変換 |
| アカウント | 専用アカウント一式 | すべて別アカウント |

## コンテンツの柱

1. **ツール実践系**: Databricks Free Edition / Snowflake / Tableau / Power BI / Looker Studio / Box / Slack / Cursor / Python を無料枠で使い倒す解説動画
2. **K-popアナリティクス**: 4大事務所 (HYBE・JYP・YG・SM) アーティストパワー指数の自動収集・分析・レポート (→ [kpop-power-index.md](kpop-power-index.md))
3. **自動化パイプライン**: データ取得→蓄積→AI要約→Slack通知→レポート出力の一気通貫デモ
4. **KPOP Analyzerサイト連携**: Google Analyticsデータを Looker Studio / Databricks / Tableau に連携したアクセス解析レポート自動化

### 公開レポート (GitHub Pages)

日次データから生成するインタラクティブHTML: [`docs/`](docs/)  
公開手順は [docs/README.md](docs/README.md)。有効化後のURL例:

`https://riverstone0228-dx.github.io/kpop_agent_power_data/`

## ドキュメント構成

- [roadmap.md](roadmap.md) — 2年ロードマップ + 3ヶ月詳細プラン
- [todo.md](todo.md) — 実行チェックリスト
- [data-sources.md](data-sources.md) — 無料で使えるデータソース・API一覧 (2026年7月調査)
- [kpop-power-index.md](kpop-power-index.md) — 4大事務所パワー指数の設計とパイプライン
- [content-plan.md](content-plan.md) — YouTube/X/note 制作・運用プラン

## アカウント戦略 (Gmail問題)

**推奨: ブランド専用Gmailを新規作成する。**

理由:

- 匿名運営が前提のため、個人アカウント (kawaishi@gmail.com) と紐づくと YouTubeチャンネル・Google Cloudプロジェクト・GA経由で身元露出のリスクがある
- 収益化・API利用規約・アカウント停止などのトラブル時に個人アカウントを巻き込まない
- 将来の英語版アカウントも同じ思想で分離できる

使い分け:

- **新規ブランドGmail**: YouTubeチャンネル、Google Cloud (YouTube API)、Looker Studio、X、note、Instagram、Databricks等の無料アカウント、Slackワークスペース
- **個人アカウント**: Gemini等での制作補助 (成果物のみブランド側へ移す)。KPOP AnalyzerのGAが個人アカウントにある場合は、ブランドGmailに閲覧権限を付与して連携

注意: ブラウザプロファイルを分ける (Chromeのプロファイル機能) と事故防止になる。
