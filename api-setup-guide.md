# APIキー取得手順 (YouTube)

⚠️ 作業は必ず**ブランド用Chromeプロファイル**(riverstone0228@gmail.com)で行うこと。
⚠️ 取得したキーは `accounts.md` に書かず、パスワードマネージャーとGitHub Secretsで管理する。

## 1. YouTube Data API v3 キー

1. [Google Cloud Console](https://console.cloud.google.com/) にriverstone0228@gmail.comでログイン
2. 画面上部のプロジェクト選択 → 「新しいプロジェクト」→ 名前を `riverstone-kpop` 等にして作成
3. 作成したプロジェクトを選択した状態で、[YouTube Data API v3のページ](https://console.cloud.google.com/apis/library/youtube.googleapis.com) を開き **「有効にする」**
4. 左メニュー「APIとサービス」→「認証情報」→ 上部 **「+ 認証情報を作成」→「APIキー」**
5. キーが表示されるのでコピー (これが `YOUTUBE_API_KEY`)
6. **そのまま「キーを制限」をクリック** → 「APIの制限」で「キーを制限」を選び、リストから **YouTube Data API v3 のみ** にチェック → 保存

補足:

- 課金設定は不要。無料枠1日10,000ユニットで動く
- 「アプリケーションの制限」はGitHub ActionsのIPが固定でないため **「なし」のままでよい**(その代わり上記のAPI制限は必ずかける)

## 2. キーの置き場所

### ローカル (Cursorでのテスト実行用)

`scripts/.env` を作成し、以下を記入 (`.gitignore`済み):

```
YOUTUBE_API_KEY=AIza...
```

### GitHub Actions (本番の日次実行用)

リポジトリ [kpop_agent_power_data](https://github.com/riverstone0228-dx/kpop_agent_power_data) → Settings → Secrets and variables → Actions → **New repository secret**:

| Name | Value |
|---|---|
| YOUTUBE_API_KEY | 上記で取得したキー |

登録済みかどうかは `accounts.md` の「GitHub Actions Secrets 登録済み一覧」でキー名だけ管理する(値は書かない)。

Apple / LINE / スペースシャワー / Wikipedia は認証不要のため Secrets 不要。

## 3. 動作確認

```bash
pip install -r scripts/requirements.txt
python scripts/resolve_artist_ids.py    # YouTube候補が出ればOK
python scripts/run_daily.py             # チャートはキー無しでも取得可
```

| 症状 | 原因 |
|---|---|
| `403 API key not valid` | APIキーのAPI制限がYouTube Data API v3になっていない |
| `403 quotaExceeded` | 1日10,000ユニット超過。翌日PT 0時にリセット |
| `.env`が読まれない | `scripts/.env` の位置が違う。scriptsフォルダ直下に置く |

## 出典

- [YouTube Data API v3](https://console.cloud.google.com/apis/library/youtube.googleapis.com?hl=ja)
