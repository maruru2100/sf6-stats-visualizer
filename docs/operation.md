# 🛠️ 運用マニュアル

日常的な使い方とトラブルシューティングです。

## 🔄 起動・停止
```bash
docker-compose up -d                          # 通常起動
docker-compose --profile external up -d       # 外部公開 + Discord Bot
docker-compose down --remove-orphans          # 停止
docker-compose up -d flyway                   # DBマイグレーションのみ
```

## 📥 データ取得
- **管理画面 (http://localhost:8501)**: ユーザー追加・削除、定期実行スケジュール変更、「今すぐ取得」、ログ確認、要望管理。
- **Discord**: `/scan_user [user] [force]`（指定ユーザー）、`/scan_all [force]`（全ユーザー）。結果は実行者のみに表示されます。
- **REST API (http://localhost:8000/docs)**: `/scrape/users/{user_code}`, `/scrape/all`, `/scrape/status`, `/schedule`, `/logs` など。`API_KEY` 設定時は `X-API-Key` ヘッダが必要です。
- 同時に実行できるジョブは1本です。実行中に要求すると 409（Botでは「現在スキャン実行中です」）となり、重複実行はされません。
- 定期巡回を止めたい場合は `.env` に `SCHEDULER_ENABLED=0` を設定します。

## 📖 コマンドの使い方確認
Discord の `/info` で、実装済みスラッシュコマンドの使い方（説明・引数）を確認できます（自分にのみ表示）。

## 🔗 公開URLの管理
- `/url`: 現在の公開URLを表示（自分にのみ表示）。
- `/update_url`: 最新URLを再取得してDBを更新。
- 管理画面、または `POST /system/public-url/refresh` でも更新できます。

## 💡 要望管理
Discord の `/request` で届いた匿名要望は、管理画面下部の「ユーザー要望管理」で完了/却下とコメントを設定できます。

## 🩺 トラブルシューティング

### 「認証切れ」と表示される / 取得できない
Cookie（`scraper/auth/local_cookies.json`）の期限切れです。Windowsホストで以下を実行し再取得してください。
```cmd
cd scraper
python auth_refresh.py
```
1. 開いているChromeを全て閉じて Enter。
2. デバッグモードで起動したChromeでバックラーにログインし、`/play` まで移動。
3. コンソールで Enter を押すと Cookie が保存されます。

※ Chromeが `C:\Program Files\Google\Chrome\Application\chrome.exe` にある前提です。

### スクレイピングが失敗する
- `GET /system/errors`、`GET /system/screenshot`（`/system/errors/{name}` で個別取得、`DELETE /system/errors` で削除）でエラー内容と画面キャプチャを確認できます。
- ログは管理画面または `GET /logs` で確認します。

### 外部URLに接続できない
PC・コンテナの再起動でURLは変わります。`/update_url` で更新し、`/url` で再確認してください。
