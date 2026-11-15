# 🥊 SF6 Stats Manager

ストリートファイター6の公式サイト「Buckler's Booty」から戦績データを自動収集し、Metabaseを用いて詳細な勝率分析やMR推移の可視化を行うためのツール一式です。

[![GitHub Pages](https://img.shields.io/badge/docs-GitHub%20Pages-blue?style=for-the-badge)](https://maruru2100.github.io/sf6-stats-visualizer/)

## 🌟 主な機能
- **自動データ収集**: Streamlit UIからの手動取得、およびスケジュール設定による定期自動実行。
- **MR推移分析**: 日次での最高MRを記録し、成長をグラフ化。
- **キャラクター別勝率**: 相手キャラごとの勝率を出し、得意・苦手なマッチアップを特定。
- **操作タイプ別分析**: モダン/クラシック別の勝率を出し、対策の進捗を確認。
- **調子の可視化**: 日別の勝率をエリアグラフで表示し、プレイの質を客観的に評価。
- **セキュアな外部共有**: Cloudflare Tunnelを利用し、固定IPやポート開放なしで仲間内にMetabaseを公開。
- **URL自動管理**: 公開用のランダムURLを自動取得し、DBへ保存。
- **Discord Bot連携**: スラッシュコマンドによるURL照会、外出先からのURL更新、およびスキャン開始（ユーザー指定／全ユーザー）に対応。
- **認証切れ検知**: Cookie期限切れ時はスキャンを中断し、Bot/管理画面へ通知。`scraper/auth_refresh.py` でCookieを再取得可能。
- **匿名要望管理**: ユーザーからの改善要望をBot経由で受け付け、管理画面で一元管理。

---

## 📖 公式ドキュメント (GitHub Pages)

詳細なセットアップ方法や分析ガイドは、以下のリンクからご確認いただけます。
> README と同じ内容を維持するよう更新しています。差異がある場合は README を優先してください。

👉 **[SF6 Stats Visualizer オンラインマニュアル](https://maruru2100.github.io/sf6-stats-visualizer/)**

---

## 🛠 テクノロジースタック
- **Python (Playwright)**: ブラウザ自動操作によるスクレイピング
- **Streamlit (frontend)**: データ収集の管理・ログ確認、および公開URL・ユーザー要望の管理GUI。REST API のクライアントとして動作します
- **FastAPI (scraper)**: スクレイピング・定期実行・ユーザー/要望管理を受け付ける REST API（Swagger: http://localhost:8000/docs ）
- **Discord.py**: 運用補助用Discord Bot
- **PostgreSQL**: 戦績データおよびシステムステータスの蓄積
- **Flyway**: データベースマイグレーション管理
- **Metabase**: BIツールによるデータビジュアライズ・ダッシュボード
- **Docker / Docker Compose**: 各マイクロサービスのコンテナ化とオーケストレーション
- **Cloudflare Tunnel (cloudflared)**: 外部公開用セキュアトンネル

## 🚀 セットアップ
- 以下の説明はWindows基準です。他OSの方は適宜読み替えてください。

### 1. リポジトリの準備
```cmd
git clone 本リポジトリ
cd sf6-stats-visualizer
```

### 2. 環境変数の設定
.env.example をコピーして .env を作成し、必要な情報を記入してください。
※ .env は Git 管理から除外（.gitignore）してください。

```cmd
copy .env.example .env
```

- TARGET_PLAYER_ID: あなたの10桁のユーザーID
- MY_PLAYER_NAME: あなたのプレイヤー名（集計用）
- DISCORD_BOT_TOKEN: Discord Developer Portalで発行したトークン
- SHARED_LOGIN_ID / SHARED_LOGIN_PW: メンバーに共有するMetabase用ログイン情報（任意）
- API_KEY: REST API の認証キー（任意）。設定すると `/health` 以外で `X-API-Key` ヘッダが必須になります。frontend / Discord Bot にも同じ値が渡されます。
- PUBLIC_URL_OVERRIDE / CF_TUNNEL_TOKEN: 独自ドメインで外部公開する場合のみ設定（任意）
- SCHEDULER_ENABLED: `0` を指定すると定期巡回を無効化します（既定: 有効）

### 3. 認証情報の配置
Playwright用のクッキー情報（local_cookies.json）を `scraper/auth/` フォルダ内に配置してください（`local_cookies.json.example` を参考）。

Cookieの期限が切れた場合（スキャン時に「認証切れ」と表示）は、Windowsのホスト上で以下を実行すると、デバッグモードのChromeからCookieを再取得できます（Chromeが `C:\Program Files\Google\Chrome\Application\chrome.exe` にある前提）。
```cmd
cd scraper
python auth_refresh.py
```
画面の案内に従ってバックラーにログインし、Enterキーを押すと `scraper/auth/local_cookies.json` が更新されます。

### 4. 起動
Dockerを使用してすべてのコンテナを起動します。

```cmd
docker-compose up -d
```

### 5.停止
```cmd
docker-compose down --remove-orphans
```

### 6.Flywayのみ適用させたいとき
```
docker-compose up -d flyway
```

## 🤖 Discord Bot コマンド
Botを導入したサーバーで以下のスラッシュコマンドが利用可能です。

- `/url`: 現在の公開URLとログイン情報を表示します。
  - **※他のユーザーには見えない（自分のみ表示）設定になっています。**
- `/update_url`: 最新の公開URLを取得し、DBを更新します。
  - **※更新完了はチャンネル内の全員に通知されます。**
- `/request [内容]`: 開発者へ匿名の改善要望を送信します。
  - **※ユーザーID等は保存されず、完全匿名で送信されます。**
- `/show_requests`: 届いている要望一覧を確認します。
- `/scan_user [user] [force]`: 指定ユーザー（候補を自動補完）のスキャンを開始します。
- `/scan_all [force]`: 登録済みの全ユーザーのスキャンを開始します。
  - **※結果は実行者にのみ表示されます。すでに実行中の場合は開始されません。Cookie切れの場合はその旨が通知されます。**

※ Botは `--profile external` 指定時に起動します。

## 📝 要望の管理
Streamlit管理画面（http://localhost:8501）の下部に「💡 ユーザー要望管理」セクションが追加されています。
ここでは以下の操作が可能です。
- **ステータス更新**: 届いた要望を「完了」または「却下」としてマーク。
- **コメント入力**: 却下理由やフィードバックを添えて更新（DBに保存されます）。

## 📊 アクセス方法
- **管理画面 (Streamlit)**: http://localhost:8501
  - ユーザーの追加・削除、定期実行スケジュールの変更、要望の管理が可能です。実行ボタンを押すとバックエンドで実行を開始します。すでに実行中の場合は「現在実行中です」と表示され、重複しては実行しません。
- **REST API (FastAPI)**: http://localhost:8000 （仕様は http://localhost:8000/docs ）
  - `.env` に `API_KEY` を設定すると、`/health` 以外は `X-API-Key` ヘッダが必須になります（フロントにも同じ値が渡されます）。
  - 主なエンドポイント: `/users`, `/scrape/users/{user_code}`, `/scrape/all`, `/scrape/status`, `/schedule`, `/logs`, `/system/public-url/refresh`, `/system/screenshot`, `/system/errors`, `/feature-requests`, `/health`
- **分析画面 (Metabase)**: http://localhost:3000
  - 初回起動時にPostgreSQL（ホスト名: `db`）との接続設定を行ってください。

## 🌐 外部共有モード (オプション)
自グループのメンバーにMetabaseを公開したい場合は、以下の手順で起動してください。

1. **公開モードで起動**
   ```bash
   docker-compose --profile external up -d
   ```
2. **URLの確認**  
  スクレイピングを1度実行（Streamlitの「今すぐ取得」等）すると、自動的に最新のURLがDBに保存されます。  
  以下のSQLで、常に最新のURLを確認できます。
   ```sql
   SELECT value FROM system_status WHERE key = 'public_url';
   ```
    ※ PCを再起動したりコンテナを上げ直すとURLが変わるため、その都度確認して共有してください。
   
   ---
    ### 最終ステップ：Metabaseでの設定
    最後に、Metabaseで以下のクエリを作成し、ダッシュボードの一番上に「テキストカード」や「単一数値」として配置してください。
    ```sql
    SELECT value FROM system_status WHERE key = 'public_url';
    ```

## ⚠️ 免責事項
- 本ツールは個人による戦績分析および学習を目的としています。
- スクレイピングの実行は、公式サイトのサーバーに負荷をかけないよう適切な頻度に設定されています。自己責任で使用してください。
- データの不整合や、サイトの仕様変更による動作停止については責任を負いかねます。

## 📝 ライセンス
このプロジェクトは [MIT License](LICENSE) の下で公開されています。