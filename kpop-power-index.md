# 4大事務所パワー指数 (K-pop Power Index)

HYBE (傘下含む)・JYP・YG・SM 所属アーティストの「パワー」を係数化し、事務所単位で比較する看板コンテンツ。

## 指標設計

詳細なデータモデル(事務所>アーティスト>楽曲のディメンション、日次スナップショット、派生指標の計算式、アクセス/エンゲージメント/アフィニティの3層フレームワーク)は [data-model.md](data-model.md) を参照。

### 収集指標 (すべて無料、詳細は [data-sources.md](data-sources.md))

| 指標 | ソース | 頻度 | 意味 |
|---|---|---|---|
| YouTube登録者数 | YouTube Data API | 日次 | ファンベース規模 |
| YouTube直近28日再生数 | YouTube Data API (動画別を集計) | 日次 | 現在の勢い |
| Wikipedia PV (ja/en) | Pageviews API | 日次 | 注目度・話題性 |
| Apple / LINE / SSTV チャート占有 | 各チャートJSON | 日次/週次 | 事務所シェア・国別人気 |
| Google Trends指数 | Trends (週次バッチ・将来) | 週次 | 検索関心 |
| Instagram/Xフォロワー | 手動記録 | 月次 | 参考値 |

### 合成方法 (v1)

1. アーティストごとに各指標を min-max または z-score で正規化
2. 加重合成: 規模系 (登録者) 50% + 勢い系 (28日再生・PV・チャート占有) 50%
3. 事務所スコア = 所属アーティストの合算 (トップ偏重を見るため上位3組版も併記)
4. 重み付けの議論自体を動画ネタにする (「BLACKPINKのパワーをどう測るか」)

### 活動休止・契約終了組の扱い (2026-07-25方針決定)

GOT7・GFRIEND・f(x)など契約終了/活動休止中のアーティストも**データ収集は全て行う**(集計に含めるかは後で判断)。理由:

- 指標を「累計・最大値」+「直近の活躍」の組み合わせで設計する構想のため、過去の実績(登録者数・総再生数などの累計系)は現在の所属有無に関わらず意味を持つ
- K-popは後輩による先輩へのオマージュ/リスペクトの文脈が頻出する (例: Hearts2Heartsがf(x)へのリスペクトを込めて楽曲を制作、等)。文脈解説コンテンツとして過去アーティストのデータも参照価値がある

集計方法(現役グループと同列に扱うか、別枠の「レジェンド指数」にするか等)は実データが貯まってから設計する。

### アーティストマスタ (v1は事務所ごと最大15組、現状HYBE13/JYP12/YG11/SM15=計51組)

マスタ本体は [scripts/artist_master.csv](scripts/artist_master.csv)。YouTubeチャンネルIDは [scripts/resolve_artist_ids.py](scripts/resolve_artist_ids.py) で候補を検索し手動確定。Apple/LINE/SSTVの外部IDは [scripts/artist_external_ids.csv](scripts/artist_external_ids.csv) で縦持ち管理。

## パイプライン構成

```
[GitHub Actions (日次cron, 無料)]
   └─ Python: YouTube / Wikipedia / Apple / LINE / Space Shower 取得
        └─ data/*.csv をリポジトリに commit・push (原本)
             └─ (Phase 4) Databricks Free Edition: Delta にも append
                  ├─ 週次 Job: 集計 + パワー指数計算
                  ├─ Databricks AI: "今日のK-popサマリー" 生成
                  │     ├─ Slack Incoming Webhook: 通知
                  │     └─ python-pptx: レポート生成 → Box アップロード
                  └─ エクスポート: JSON → GitHub Pages の HTML ダッシュボード
```

### 閾値アラート例 (Slack通知)

- 登録者・フォロワーがキリ番 (100万単位) 突破
- 週次成長率が過去平均の2倍以上
- Wikipedia PVが前週比3倍 (話題化検知)

## HTML「4大事務所パワー比較」サイト

- GitHub Pages + Chart.js で静的サイト。日次JSONを読み込むだけの構成 (サーバー不要・無料)
- レーダーチャート (事務所×指標)、時系列ライン、アーティストランキング
- サイト自体がポートフォリオ兼コンテンツ。「このサイトの作り方」動画シリーズにできる
- KPOP Analyzerサイトと相互リンクし、GAでどちらも計測 → 「自サイトのGA分析」動画へ循環

## KPOP Analyzer 連携 (別プロジェクト)

- GA4 → Looker Studio: 定番の無料レポート自動化 (動画ネタ第1候補、難易度低)
- GA4 → BigQuery無料枠 → Databricks/Tableau: 中級ネタ
- 「パワー指数記事を公開したらアクセスがどう動いたか」を自己分析する動画はメタ的で面白い
