# チャート系データソースの検証結果と推奨方針

作成: 2026-07-26 / 関連: [data-sources.md](data-sources.md) / [spotify-api-change-2026.md](spotify-api-change-2026.md)

ご提案の6ソースを実際にアクセスして技術的可否・規約リスクを検証した結果。

## 総合判定 (2026-07-26 robots.txt実地確認済み)

| ソース | 技術的可否 | robots.txt | 判定 |
|---|---|---|---|
| Apple Music RSS (jp/kr/us) | 公式無料JSON API | 対象外(公式API) | ✅ **最優先で実装** |
| スペースシャワーTV | JS描画 (要ヘッドレス) | GPTBotの/login/,/mypage/のみ禁止。**ランキングページは許可** | ✅ **実装可** |
| レコチョク | JS描画 (要ヘッドレス) | robots.txt取得できず(空) | △ ToS確認の上で可 |
| LINE MUSIC | JS描画 (要ヘッドレス) | robots.txtなし(SPAの404が返る) | △ ToS確認の上で可 |
| **Melon (韓国)** | 海外IPからは古いデータが返る | **`User-agent: * → Disallow: /`** | ❌ **明確な拒否。実施しない** |
| Spotify | API変更で指標取得不可 | — | ❌ **不使用** ([spotify-api-change-2026.md](spotify-api-change-2026.md)) |

---

## 1. Apple Music → 公式RSS APIを使う (スクレイピング不要)

`music.apple.com` のチャートページはJavaScript描画のため、HTMLを取得しても順位リストは入っていない(メタ情報に上位3曲が出るのみ)。しかし **Appleは公式の無料RSSフィードAPIを提供している**。

```
https://rss.marketingtools.apple.com/api/v2/jp/music/most-played/100/songs.json
```

- 認証不要・完全無料・JSON形式
- 各曲に `artistName` / `name` / `artistId` / `releaseDate` / `genres` が含まれる
- 国コード(`jp`/`kr`/`us`)を変えるだけで各国チャートが取れる → **日韓米の比較は極めて強力なコンテンツになる**

### 韓国チャート(kr)の検証結果 — 想定以上に良い

`.../api/v2/kr/music/most-played/100/songs.json` を実際に取得したところ、TOP10のうち9曲がK-popで、CORTIS・Hearts2Hearts・aespa・RESCENE・ILLITなど**こちらのマスタ掲載アーティストがそのまま並んでいました**。さらに重要な発見が2つ:

**発見1: ジャンルタグでK-popを判別できる**

各曲の `genres` 配列に `{"genreId":"51","name":"K-Pop"}` が入っています。つまりRSSは総合チャートですが、**genreId=51でフィルタすればK-popだけを抽出できます**。ジャンル別チャートが取れないという当初の制約は、実質的に解消されました。

**発見2: `artistId` で言語をまたいで名寄せできる**

韓国版ではアーティスト名が韓国語表記になります(CORTIS→코르티스、RESCENE→리센느、ILLIT→아일릿)。名前での突合は破綻しますが、**`artistId` はどの国でも同一**です(例: ILLITはjp/kr両方で `1734551937`)。

→ **`artist_master.csv` に `apple_artist_id` 列を追加すべきです。** 一度これを埋めれば、日韓米すべてのチャートで確実に名寄せできます。

### 作れる指標

- 各国の総合TOP100のうちK-pop曲数 = **国別「K-popシェア」**
- そのうちHYBE/JYP/YG/SMが何曲ずつか = **事務所別チャート占有率**
- **同じ曲の日本順位 vs 韓国順位 vs 米国順位の乖離** ← これが一番面白い。「韓国で1位でも日本で圏外の曲」「日本だけで伸びる曲」の分析は他の誰もやっていない切り口

⚠️ 注意: 検証時、jp版の `updated` が約1ヶ月前、kr版も同様に古めの日付でした。日次更新でない可能性があるため、稼働後に実際の更新間隔を必ず確認してください。

## 2. Spotify → 不使用

2026年2月のAPI変更により必要な指標が取得不可のため、本プロジェクトでは使わない。記録のみ: [spotify-api-change-2026.md](spotify-api-change-2026.md)

## 2.5 Melon (韓国) → 実施しない

`melon.com/robots.txt` を確認した結果、明確な拒否がありました。

```
User-agent: *
Disallow: /
```

Googlebot・daumoa・Applebot・Yeti(Naver)など**名指しされた検索エンジンにのみ特定パスを開放**し、それ以外のすべてのクローラーをサイト全体で拒否する設定です。私たちのスクレイパーは `User-agent: *` に該当するため、**サイト運営者から明示的に「来ないでほしい」と表明されている**状態になります。

加えて実務上の問題として、海外IPからチャートページを取得したところ **2016年10月時点の古いデータ**が返ってきました。地域制限またはキャッシュにより、そもそも海外からは最新チャートを取得できない可能性が高いです。

技術的な回避手段(韓国プロキシ等)は存在しますが、**robots.txtで明示的に拒否されているサイトを迂回してまで取得するのは、リバーストーンの看板に傷がつきます**。「規約を確認して、ダメなものはやらない」判断ができること自体がデータ専門家の価値なので、ここは見送りましょう。

**韓国の人気は Apple Music kr チャートでカバーできます**(上記の通り、K-popジャンルタグ付きで取得可能)。加えて、韓国の公式チャート機関である **Circle Chart (旧Gaon、[circlechart.kr](https://circlechart.kr/))** は日本のオリコンに相当する立場で、データの二次利用条件を問い合わせられる可能性があります。将来的な選択肢として記録しておきます。

## 3. 日本チャート: LINE MUSIC + スペースシャワー (2026-07-26更新)

**正式ソース (ユーザー指定)**:

| ソース | エントリURL | 実エンドポイント | 粒度 |
|---|---|---|---|
| LINE MUSIC K-Pop Top 50 | https://music.line.me/webapp/ranking-genre/mg0000000000000033 | `music.line.me/api2/chart/genre/mg0000000000000033/tracks.v1` | 日次・50曲 |
| スペースシャワー KOREAN HITS | https://tv.spaceshower.jp/p/00089521/ | `tv.spaceshower.jp/p/chart/00089521/chart.json` | 週次・40曲 |

**robots.txt確認結果 (2026-07-26)**:

- **スペースシャワーTV**: `User-agent: GPTBot` に対して `/login/` `/mypage/` のみ禁止。**ランキングページの取得は許可されている** → 問題なし
- **LINE MUSIC**: robots.txtのパスがSPAの404ページを返す。実質robots.txtなし
- **レコチョク**: 今回スコープ外(後回し)。robots.txtは空レスポンスだった

### 重要: Playwrightは不要

当初はJS描画のためPlaywrightが必要と判断していたが、両ソースとも **認証不要のJSONエンドポイント** が公開されており、`requests` だけで取得できる。実装は [scripts/fetch_line_charts.py](scripts/fetch_line_charts.py) / [scripts/fetch_spaceshower_charts.py](scripts/fetch_spaceshower_charts.py)。

### 外部ID管理

LINEは同一アーティストに複数 `artistId` (`mi...`) が付くことがあるため、マスタCSVへの単一列追加はしない。縦持ちの [scripts/artist_external_ids.csv](scripts/artist_external_ids.csv) で管理し、チャート採掘は [scripts/mine_chart_ids.py](scripts/mine_chart_ids.py)。

### 運用条件

1. **各サイトの利用規約を事前に確認**する(自動取得の禁止条項の有無)
2. `robots.txt` を尊重する
3. **1日1回に限定**(SSTVは週次更新なので日次実行しても同一JSONの再取得になる)
4. User-Agentに連絡先を明記する
5. **順位表をそのまま再公開しない**

## ⚠️ 最重要: 「収集」と「再公開」は別問題

私は弁護士ではないため確定的なことは言えませんが、実務上とても重要な論点なので共有します。

- **個々の順位という事実そのもの**は、一般に著作権の対象になりにくいとされます
- しかし**ランキング表という「まとまり」**は、日本の著作権法上「データベースの著作物」(第12条の2)として保護される可能性があります
- つまり **「自分の分析のために集める」と「ランキング表を丸ごとサイトやYouTubeに再掲する」は、リスクの水準が全く違います**

**推奨する運用**: 生の順位表は再公開せず、**そこから導いた指標だけを見せる**。例えば:

- ❌ 「LINE MUSIC K-Pop Top 50」をそのまま表示
- ✅ 「日本の主要サービスで、HYBE系アーティストのランクイン曲数はこの3ヶ月でこう推移した」

後者の方が分析として価値が高く、リスクも低く、そしてリバーストーンらしいコンテンツです。出典表記も必ず行ってください。

## 推奨する実装順序

1. **Apple Music RSS API** (認証不要・規約クリア・すぐ動く) — jp / kr / us の3カ国を日次取得
2. YouTube API + Wikipedia PV の既存パイプラインを安定稼働させる
3. **スペースシャワーTV + LINE MUSIC** — JSONエンドポイントで実装 (Playwright不要)
4. **レコチョク** — 後回し
5. Melon・Spotifyチャートは実施しない

## 次のアクション

- [x] `scripts/fetch_apple_charts.py` を作成 (2026-07-26。jp/kr/us、genreId=51でK-pop判定、国×事務所の集計まで出力)
- [x] `artist_master.csv` / `other_agency_master.csv` に **`apple_artist_id` 列を追加** (2026-07-26)
- [x] `scripts/resolve_apple_artist_ids.py` を作成 (2026-07-26。iTunes Search APIで候補検索)
- [x] Apple artist ID確定 + 初回 `fetch_apple_charts.py` 実行 (2026-07-26)
- [x] LINE / スペースシャワー JSON取得スクリプト + 外部ID縦持ち設計 (2026-07-26)
- [ ] `mine_chart_ids.py` の候補から人手で `confirmed` を確定し続ける
- [ ] 各サイトのフッターにある利用規約に自動取得の禁止条項がないか目視確認
- [ ] 取得は1日1回・低頻度、User-Agentに連絡先を明記

## 取得実装時の作法 (必ず守る)

```python
# User-Agentに正体と連絡先を明記する = 誠実な運用の証明
USER_AGENT = "riverstone-kpop-index/0.1 (research use; riverstone0228@gmail.com)"
```

- 1日1回のみ実行、ページ間は2〜3秒待つ
- 取得失敗時に自動リトライを繰り返さない(サーバー負荷になる)
- サイト側から連絡があれば即座に停止する
- **生の順位表を再公開せず、導出指標のみ公開する**(上記の著作権の注意点を参照)
