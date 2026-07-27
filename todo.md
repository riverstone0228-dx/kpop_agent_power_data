# TODO チェックリスト

## Month 1: 基盤 (7/27〜8/23)

### アカウント (W1)
- [x] ブランド用Gmail新規作成 (リバーストーン名義) → riverstone0228@gmail.com (2026-07-25)
- [x] Chromeプロファイルをブランド用に分離 (2026-07-25)
- [x] YouTubeチャンネル開設 (新Gmail) → 「リバーストーン | AI×データ分析」 @riverstone_dx (2026-07-25)
- [x] X / note アカウント開設 (2026-07-25) / Instagramは未
- [ ] アイコン・バナー・カラー決定 (全媒体統一)

### ツール開設 (W1-2)
- [x] Databricks Free Edition (2026-07-25)
- [x] GitHub (リポジトリ作成 2026-07-25: [kpop_agent_power_data](https://github.com/riverstone0228-dx/kpop_agent_power_data)) — Actions/Pages設定は未
- [x] Slackワークスペース作成 (2026-07-25)、Incoming Webhook作成は未
- [x] Box (個人無料) 登録 (2026-07-25) / Tableau Public・Looker Studioは未
- [x] Google Cloud プロジェクト作成 (新Gmail) + YouTube Data APIキー (2026-07-25)
- [x] Spotify不使用を確定 (2026-07-26) → [spotify-api-change-2026.md](spotify-api-change-2026.md)

### データ収集開始 (W2-3) ★最優先
- [x] アーティストマスタCSV雛形作成 (4事務所・計51組+TWS、2026-07-26更新) → [scripts/artist_master.csv](scripts/artist_master.csv)
- [x] sub_agency(傘下レーベル)ディメンション追加 (2026-07-25) — HYBE/JYPの各レーベルをマッピング
- [x] 他事務所TOP15候補プール作成 → [scripts/other_agency_master.csv](scripts/other_agency_master.csv) (目標20-30組、現状17組)
- [x] 2マスタ統合モジュール作成 → [scripts/master_data.py](scripts/master_data.py)
- [x] rank_other_agency_top15.py — チャート勢い70%+YouTube30%+ヒステリシス
- [ ] resolve_artist_ids.pyで youtube_channel_id 確定 (手動確認待ち)
- [ ] 要確認リストのファクトチェック (NewJeans/iKON/G-DRAGON/GFRIEND/GOT7/fromis_9/f(x)/MEOVVのYG関係等)
- [x] 日次取得パイプライン作成 (YouTube/Wikipedia/Apple/LINE/SSTV → run_daily.py)
- [x] GitHub Actions workflow雛形作成 (.github/workflows/daily_collect.yml)
- [x] 楽曲マスタ設計確定 (タイトル曲のみ) → [data-model.md](data-model.md)
- [x] seed_track_master.py — YouTube TOP10 + チャート出現曲で候補生成
- [ ] **[要ユーザー作業]** `scripts/.env` に YOUTUBE_API_KEY を設定 → resolve_artist_ids.py 実行 → チャンネルID確定
- [ ] コードとマスタを kpop_agent_power_data に push、GitHub Secrets に `YOUTUBE_API_KEY` を登録
- [ ] workflow_dispatchで手動実行テスト → 問題なければcron本稼働
- [ ] youtube_channel_id確定後、seed_track_master.py実行 → track_master.csvを確定
- [x] チャート系: Apple + LINE + スペースシャワー採用 (Melon見送り、レコチョク後回し)
- [x] fetch_apple / fetch_line / fetch_spaceshower / mine_chart_ids / 外部ID縦持ち
- [ ] artist_external_ids.csv の unmatched を人手で confirmed へ確定し続ける
- [ ] Databricks Deltaテーブルへ書き込み ([databricks/README.md](databricks/README.md) · Free Edition: Volume → Notebook)
- [ ] Slack通知 (取得成功/失敗 + キリ番アラート + 他事務所TOP15入れ替えアラート)

### 制作環境 (W3-4)
- [ ] OBS + アバター口パク環境のセットアップ
- [ ] 音声加工 (低音化) の設定確定・保存
- [ ] 30秒テスト収録で「別人に見える/聞こえる」確認

## Month 2: パイプライン+練習 (8/24〜9/20)

- [ ] パワー指数計算ロジック (正規化+加重) 実装、週次Job化
- [ ] Databricks AIで日次サマリー生成 → Slack通知
- [ ] python-pptx月次レポート → Boxアップロード自動化
- [ ] HTMLダッシュボードv1 (GitHub Pages + Chart.js)
- [ ] テスト動画1本を通しで制作 (限定公開)
- [ ] 制作フローの改善点を反映、所要時間を記録
- [ ] note下書き2本 / X運用ルール (投稿頻度・トーン) 決定
- [ ] GA4 (KPOP Analyzer) → Looker Studio レポート作成

## Month 3: ストック+公開 (9/21〜10/31)

- [ ] 本番動画3本ストック (①指数初公開 ②Databricks解説 ③GA×Looker)
- [ ] サムネ・概要欄テンプレ完成
- [ ] HTMLダッシュボード公開
- [ ] X でティザー投稿開始 (公開2週間前)
- [ ] **10月最終週: YouTube第1弾 + note + X 同時公開**
- [ ] 公開後1週間の初速データ分析 → 次の動画ネタに

## 検討中 / 保留

- [ ] Snowflake 30日トライアル企画 (公開後、2027年に)
- [ ] Power BI Desktopデモ動画
- [ ] 英語版ペルソナ・翻訳パイプライン (2027 Q3)
- [ ] 収益化と匿名性の両立方法の調査 (登録者が伸びてから)
