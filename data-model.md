# データモデル設計 (事務所 > アーティスト > 楽曲)

関連: [kpop-power-index.md](kpop-power-index.md) / [data-collection-plan.md](data-collection-plan.md) / [scripts/artist_master.csv](scripts/artist_master.csv)

## 全体構造

```
dim_agency (事務所: HYBE/JYP/YG/SM/OTHER)
  └─ dim_sub_agency (レーベル: BIGHIT MUSIC, SOURCE MUSIC, THE BLACK LABEL, Starship...)
       └─ dim_artist (アーティスト)
            └─ dim_track (楽曲・タイトル曲のみ)

fact_artist_daily  (アーティスト単位・日次スナップショット)
fact_track_daily   (楽曲単位・日次スナップショット)
      ↓ (SQL/ウィンドウ関数で集計時に計算、rawでは持たない)
派生指標: 直近7日/28日、いいね率、成長率 など
```

2026-07-25更新: **sub_agency(傘下レーベル)ディメンションを追加**。HYBEはBIGHIT MUSIC/SOURCE MUSIC/PLEDIS/BELIFT LAB/ADOR/KOZ等の複数レーベルを持つマルチレーベル体制のため、事務所(agency)とレーベル(sub_agency)を分けて持つことで「HYBE全体」と「レーベル別」の両方の切り口で集計できる。同じ仕組みを使って **agency="OTHER"(4大事務所以外)** も表現し、sub_agencyに実際のレーベル名(Starship, THE BLACK LABEL, THE MUZE等)を入れる設計に統一した。

**設計方針**: 毎日GETするのは「その時点の累積値」(スナップショット)のみ。直近7日/28日/成長率などは**生データとして保持せず、集計層(SQL/Databricksのview)で当日値と過去日の差分から都度計算**する。これによりraw側のスキーマがシンプルなまま保たれ、集計ウィンドウを後から自由に変えられる。

## ディメンション (Dimension = 何を評価するかの軸)

### dim_agency

| 列名 | 型 | 説明 |
|---|---|---|
| agency_id | PK | |
| agency_name | string | HYBE / JYP / YG / SM / **OTHER** (4大事務所以外の候補プール、詳細は後述) |

### dim_sub_agency (傘下レーベル・新規)

| 列名 | 型 | 説明 |
|---|---|---|
| sub_agency_name | string | 実際のレーベル名 (例: BIGHIT MUSIC, SOURCE MUSIC, ADOR, KOZ Entertainment, THE BLACK LABEL, Starship Entertainment...) |
| agency_id | FK | 親事務所 (OTHERの場合もagency=OTHERのまま、sub_agencyに実レーベル名) |

HYBE内のマッピング例: BTS/TXT/CORTIS→BIGHIT MUSIC、SEVENTEEN→PLEDIS、ENHYPEN/ILLIT→BELIFT LAB、LE SSERAFIM/GFRIEND→SOURCE MUSIC、NewJeans→ADOR、BOYNEXTDOOR→KOZ Entertainment、&TEAM→HYBE LABELS JAPAN、KATSEYE→HYBE America(Geffen Records)。JYPもVCHA→JYP USA、OURBIRTHDAY→INNIT Entertainmentのようにサブレーベルを持つ。

⚠️ **fromis_9とGOT7は要判断**: fromis_9は2024年末にPLEDIS(HYBE)との契約が終了し現在HYBE非所属、GOT7も2021年にJYPとの契約終了済み。収集は継続するが(累積指標・オマージュ文脈の価値があるため)、事務所別集計に含めるかはstatus列で個別管理する([scripts/artist_master.csv](scripts/artist_master.csv)参照)。

### dim_artist

| 列名 | 型 | 説明 |
|---|---|---|
| artist_id | PK | |
| agency_id | FK | |
| sub_agency | string | 傘下レーベル (上記参照) |
| artist_name_en / artist_name_ja | string | |
| artist_type | string | group / solo / unit |
| debut_date | date | |
| status | string | active / inactive / disbanded / pre-debut |
| youtube_channel_id | string | |
| apple_artist_id | string | **国をまたいだ名寄せの鍵**。韓国ストアではアーティスト名が韓国語表記(ILLIT→아일릿)になるため、名前ではなくこのIDで突合する。IDは全世界共通 |
| wikipedia_title_ja / en | string | |

⚠️ Spotifyはデータソースから除外済み ([spotify-api-change-2026.md](spotify-api-change-2026.md))。

⚠️ **`line_artist_id` / `spaceshower_artist_id` はマスタ本体に直置きしない。** LINEは同一アーティストに複数IDが付くことがあり、横持ち1列では名寄せが破綻する。外部IDは下記の縦持ちマップで管理する。

(現状 [scripts/artist_master.csv](scripts/artist_master.csv) (4大事務所) + [scripts/other_agency_master.csv](scripts/other_agency_master.csv) (他事務所候補プール) がこのディメンションの実体。2つのマスタは [scripts/master_data.py](scripts/master_data.py) が結合して読み込む)

### artist_external_ids (プラットフォーム横断の名寄せマップ) 🆕

[scripts/artist_external_ids.csv](scripts/artist_external_ids.csv)。PK相当は `(platform, external_artist_id)`。

| 列名 | 説明 |
|---|---|
| platform | `line` / `spaceshower` (将来 `apple` も移行可) |
| external_artist_id | 例: LINE=`mi000000000dcc9b82` / SSTV=`020394` |
| artist_name_en | マスタ側の正規名 (未確定時は空) |
| source_file | `artist_master.csv` / `other_agency_master.csv` |
| match_status | `confirmed` / `candidate` / `unmatched` |
| observed_name | チャート上の表記 |
| first_seen / last_seen | 初出・最終確認日 |
| notes | 別名・重複IDなど |

取得フロー: チャートJSONを採掘 (`mine_chart_ids.py`) → 名前正規化で自動マッチ → 人手で `confirmed` 確定。同一アーティストに複数LINE IDがある場合は同じ `artist_name_en` で複数行を `confirmed` にする。

### track_external_ids (チャート出現曲のIDレジストリ) 🆕

[scripts/track_external_ids.csv](scripts/track_external_ids.csv)。`(platform, external_track_id)` → `artist_name_en` + `track_name`。

- `track_master.csv` = 「追いたい楽曲」の canonical マスタ (`track_id` 付き。チャート横断＋代表MV)
- `track_external_ids.csv` = 「チャートに出た曲のIDレジストリ」(apple / line / spaceshower → アーティスト・曲名)

初期構築: [scripts/mine_chart_ids.py](scripts/mine_chart_ids.py) → [scripts/build_track_master.py](scripts/build_track_master.py)  
日次ランキング: [scripts/rank_songs.py](scripts/rank_songs.py) → `data/song_rankings/top_*.csv` / `hot_*.csv`

| ランキング | 意味 | 主指標 |
|---|---|---|
| TOP SONG 20 | 定着・総合力 | 直近7日チャート加点 + YouTube累積再生 |
| HOT SONG 20 | 勢い | 直近3日−前3日のチャートデルタ + 新規/上昇ボーナス + YTエンゲージメント |

### 「他事務所TOP15」インデックスの設計

4大事務所以外のK-popアーティストも、趣味的な観点も含めてなるべく多く貯める方針(2026-07-25決定)。ただし比較コンテンツとしては「TOP15」に絞って見せたいので、**株価指数のような設計**にした。

- `other_agency_master.csv` は**候補プール** (目標 **20〜30組**。現状17組)。15組ちょうどである必要はない
- 集計・ダッシュボード・動画で見せる「OTHER」は **TOP15のみ**
- 選定ロジック (2026-07-26改定) → [scripts/rank_other_agency_top15.py](scripts/rank_other_agency_top15.py)

| 要素 | 内容 |
|---|---|
| 主指標 70% | **チャート勢い**: LINE(直近7日) + スペースシャワー(直近2週) + Apple jp/kr K-Pop(直近7日)。各出現で `(chart_size - rank + 1)` を加点 |
| 副指標 30% | **YouTube登録者**の log1p をプール内正規化 (未取得時はチャート100%) |
| ヒステリシス | 新規は当日14位以内、既存は17位以下に落ちたときだけ除外 → 境界の日次チラつきを抑制 |
| コンテンツ化 | 前日比の「新規ランクイン / ランク外」を changelog に記録 |

⚠️ **TWSについて**: ユーザー指定で候補に挙がったが、PLEDIS(HYBE)所属のため OTHER ではなく [artist_master.csv](scripts/artist_master.csv) の HYBE に分類 (CORTISと同じ扱い)。
✅ **izna / PLAVE / YENA**: チャート初出をきっかけに OTHER プールへ追加 (2026-07-26)。

⚠️ **CORTISについて**: 調査の結果、CORTISは実際にはBIGHIT MUSIC(HYBE)所属と判明したため、「他事務所」ではなくHYBE側のartist_master.csvに分類しました。
✅ **MEOVV/THE BLACK LABELについて**: THE BLACK LABELはYGが出資しTEDDY氏が設立したレーベルのため、2026-07-25にユーザー指示で「他事務所」からYG(sub_agency=THE BLACK LABEL)へ移動しました。

### dim_track (楽曲マスタ) — 2026-07-25方針確定: **タイトル曲のみ追跡**

| 列名 | 型 | 説明 |
|---|---|---|
| track_id | PK | |
| artist_id | FK | |
| track_name_en / track_name_ja | string | |
| release_date | date | カムバック分析・経過日数の起点 |
| track_type | string | title(タイトル曲)固定運用 |
| youtube_video_id | string | 公式MV等の動画ID |
| selection_reason | string | 下記の初期選定ロジックのどれで採用されたか (複数該当あり) |
| is_active_tracking | bool | 追跡対象かどうか |

**初期選定ロジック (ブートストラップ、[scripts/seed_track_master.py](scripts/seed_track_master.py))**: 各アーティストにつき次のいずれかに該当する曲を候補とする。

1. YouTube公式ch内の累積再生数TOP10動画 (`search.list(order=viewCount)`)
2. Apple / LINE / スペースシャワーのチャートに出現した曲 (master突合済み)

候補を`track_candidates_report.csv`に出力し、人が`track_master.csv`に確定する。一度確定した後は、新曲リリースのたびにその曲(=最新のタイトル曲)だけを追加していく運用。

## ファクト (Value = 実際にGETして貯める数値)

### fact_artist_daily (grain: 1行 = 1アーティスト×1日)

| 列名 | ソース | 性質 |
|---|---|---|
| date, artist_id | — | キー |
| youtube_subscribers | YouTube `channels.list` | 累積(スナップショット) |
| youtube_channel_total_views | YouTube `channels.list` | 累積 |
| youtube_video_count | YouTube `channels.list` | 累積 |
| wikipedia_pv_ja / en | Wikipedia Pageviews | **当日値** (もともと日次カウント) |
| google_trends_index | Google Trends (週次・将来) | 相対指数0-100 |

### fact_apple_chart_daily (grain: 1行 = 1国×1順位×1日) 🆕

[scripts/fetch_apple_charts.py](scripts/fetch_apple_charts.py) が出力。

| 列名 | 説明 |
|---|---|
| date, country, rank | キー (country = jp/kr/us) |
| track_name, artist_name_local | チャート上の表記 (韓国版は韓国語) |
| apple_artist_id, apple_track_id | 名寄せ用ID |
| is_kpop_genre | genreId=51 が付いているか |
| agency, sub_agency, artist_name_master | マスタと突合できた場合に付与 |

ここから導かれる指標:

- **国別K-popシェア** = TOP100中のK-pop曲数
- **事務所別チャート占有率** = 国×事務所のランクイン曲数
- **国間の順位乖離** = 同一 `apple_track_id` の jp / kr / us 順位差 ← 最も独自性が高い指標

### fact_line_chart_daily (grain: 1行 = 1順位×1日) 🆕

出典エントリ: [LINE MUSIC K-Pop Top 50](https://music.line.me/webapp/ranking-genre/mg0000000000000033)
実エンドポイント: `https://music.line.me/api2/chart/genre/mg0000000000000033/tracks.v1` (認証不要JSON、Playwright不要)

[scripts/fetch_line_charts.py](scripts/fetch_line_charts.py) → `data/line_charts/YYYY-MM-DD.csv`

| 列名 | 説明 |
|---|---|
| date, rank | キー |
| track_name, artist_name_local | チャート上の表記 |
| line_artist_id, line_track_id | 名寄せ用 (`mi...` / `mt...`) |
| score, listened_count, like_count | チャートスコア・累積再生・いいね |
| agency, sub_agency, artist_name_master | `artist_external_ids` 経由で突合できた場合に付与 |

### fact_spaceshower_chart_weekly (grain: 1行 = 1順位×放送日) 🆕

出典エントリ: [スペースシャワーTV KOREAN HITS RANKING](https://tv.spaceshower.jp/p/00089521/)
実エンドポイント: `https://tv.spaceshower.jp/p/chart/00089521/chart.json` (週次・40曲。履歴は `.../YYYYMMDD/chart.json`)

[scripts/fetch_spaceshower_charts.py](scripts/fetch_spaceshower_charts.py) → `data/spaceshower_charts/YYYY-MM-DD.csv` (ファイル日付は放送日)

| 列名 | 説明 |
|---|---|
| chart_date, rank | キー |
| track_name, artist_name_local | チャート上の表記 |
| spaceshower_artist_id, spaceshower_song_id | 名寄せ用 (数字ID) |
| agency, sub_agency, artist_name_master | `artist_external_ids` 経由で突合 |

レコチョクは今回スコープ外(後回し)。将来Deltaでは `fact_chart_daily(platform, chart_id, ...)` に統合予定。

### fact_track_daily (grain: 1行 = 1楽曲×1日)

| 列名 | ソース | 性質 |
|---|---|---|
| date, track_id | — | キー |
| youtube_views_cum | YouTube `videos.list` | 累積 |
| youtube_likes_cum | YouTube `videos.list` | 累積 |
| youtube_comments_cum | YouTube `videos.list` | 累積 |

⚠️ YouTubeのlikeCount/commentCountは投稿者が非公開設定にしている場合は取得できません(主要K-pop公式chは通常公開)。

## 派生指標 (集計層で計算、生データとしては持たない)

`fact_track_daily` の累積値から、当日と N日前の差分を取るだけで作れます。

| 指標 | 計算式 |
|---|---|
| 直近7日再生数 | `views_cum(t) - views_cum(t-7)` |
| 直近28日再生数 | `views_cum(t) - views_cum(t-28)` |
| 直近7日いいね数 | `likes_cum(t) - likes_cum(t-7)` (28日も同様) |
| 直近7日コメント数 | `comments_cum(t) - comments_cum(t-7)` (28日も同様) |
| いいね率 | `直近7日いいね数 / 直近7日再生数` |
| コメント率 | `直近7日コメント数 / 直近7日再生数` |
| エンゲージメント率 | `(直近7日いいね数 + 直近7日コメント数) / 直近7日再生数` |
| 登録者増加数 | `subscribers(t) - subscribers(t-7 or t-28)` |
| 週次成長率(勢い) | `直近7日再生数(今週) / 直近7日再生数(先週) - 1` |
| 登録者あたり累積再生 | `youtube_channel_total_views / youtube_subscribers` (下記アフィニティ参照) |

## 3層フレームワーク: アクセス / エンゲージメント / アフィニティ

ご相談の「アクセス・エンゲージメント・好き度」を指標グループとして整理すると、以下のように対応づけられます。

| 層 | 意味 | 使う指標 |
|---|---|---|
| **アクセス (Reach)** | どれだけ多くの人に届いているか | 登録者数・フォロワー数・累積再生数・Wikipedia PV・Google Trends指数 |
| **エンゲージメント (Engagement)** | 届いた人がどれだけ反応したか | いいね率・コメント率・エンゲージメント率 (直近7日/28日) |
| **アフィニティ/ロイヤリティ (Affinity)** | 一過性でなく継続的に応援されているか | 登録者あたり累積再生 (潜在ファンの濃さ)、カムバックごとの初速安定性、プロモ無し日のTrends/Wikipedia上昇 (=自然発生的な話題) |

パワー指数は将来的にこの3層をそれぞれスコア化し、`Power = w1×Access + w2×Engagement + w3×Affinity` のような加重合成にすると説明しやすく、動画でも「3つのレンズで見るK-popパワー」という切り口にできます。

## 実装状況 (2026-07-26更新)

| ファイル | 役割 |
|---|---|
| [scripts/artist_master.csv](scripts/artist_master.csv) | 4大事務所アーティストマスタ (sub_agency列あり、計51組) |
| [scripts/other_agency_master.csv](scripts/other_agency_master.csv) | 他事務所候補プール (現在14組、増減自由) |
| [scripts/master_data.py](scripts/master_data.py) | 上記2ファイルを結合して読み込む共通モジュール |
| [scripts/artist_external_ids.csv](scripts/artist_external_ids.csv) | LINE/SSTV等の外部アーティストIDマップ (縦持ち) |
| [scripts/track_external_ids.csv](scripts/track_external_ids.csv) | チャート出現曲の外部トラックIDレジストリ |
| [scripts/track_master.csv](scripts/track_master.csv) | 楽曲マスタ (雛形のみ、seed_track_master.py実行後に確定) |
| [scripts/seed_track_master.py](scripts/seed_track_master.py) | 楽曲マスタの初期候補を3条件で自動生成 |
| [scripts/rank_other_agency_top15.py](scripts/rank_other_agency_top15.py) | 他事務所候補プールから実データでTOP15を日次決定 |
| [scripts/fetch_youtube.py](scripts/fetch_youtube.py) / [fetch_wikipedia.py](scripts/fetch_wikipedia.py) / [run_daily.py](scripts/run_daily.py) | アーティスト単位の日次取得パイプライン |
| [scripts/fetch_apple_charts.py](scripts/fetch_apple_charts.py) / [fetch_line_charts.py](scripts/fetch_line_charts.py) / [fetch_spaceshower_charts.py](scripts/fetch_spaceshower_charts.py) | チャート系日次/週次取得 |
| [scripts/mine_chart_ids.py](scripts/mine_chart_ids.py) | チャートJSONから外部IDを採掘し候補レポートを生成 |

未着手: 楽曲単位(fact_track_daily)の日次取得スクリプト。track_master.csvが確定次第作成する。
