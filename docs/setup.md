# 🚀 セットアップガイド

このプロジェクトを自身の環境で構築し、戦績データの収集と分析を開始するための手順を解説します。
※ Windows 環境を基準に説明していますが、Dockerが動作する環境であれば Mac/Linux でも同様に構築可能です。

---

## 📋 1. 事前準備

### 必須ツール
- **Git**: リポジトリのクローンに使用します。
- **Docker / Docker Compose**: アプリケーション、データベース、分析ツールをコンテナで起動します。

### 必要な情報
- **TARGET_PLAYER_ID**: あなたの10桁のユーザーID。
- **MY_PLAYER_NAME**: あなたのプレイヤー名（集計表示用）。
- **local_cookies.json**: バックラーズメイルにログインするための認証クッキー。
  - ブラウザのデベロッパーツール等で取得し、`./auth/` フォルダ内に配置してください。

## 🛠️ 2. インストール手順

### リポジトリのクローン
コマンドプロンプトやターミナルで以下を実行します。
```cmd
git clone [https://github.com/maruru2100/sf6-stats-visualizer.git](https://github.com/maruru2100/sf6-stats-visualizer.git)
cd sf6-stats-manager
```

### 環境変数の設定
.env.example をコピーして .env を作成し、エディタで開いて自身の情報を記入します。
```bat
copy .env.example .env
```

主要な設定項目:
- DISCORD_BOT_TOKEN: Discord Botを使用する場合に設定。
- SHARED_LOGIN_ID / SHARED_LOGIN_PW: メンバーに共有するMetabase用ログイン情報（任意）

## 🚢 3. サービスの起動

Dockerを使用して、すべてのコンテナ（DB、スクレイパー、Metabase、Flyway等）を一括起動します。

```bash
docker-compose up -d
```

### 起動後のアクセス先
- **管理画面 (Streamlit)**: http://localhost:8501
  - ユーザーの追加・削除、定期実行スケジュールの変更、要望の管理が可能です。「今すぐ取得」ボタンを押すと即座にスクレイピングが始まります。
- **分析画面 (Metabase)**: http://localhost:3000
  - 初回起動時にPostgreSQL（ホスト名: `db`）との接続設定を行ってください。

## 📊 4. Metabase の初期設定

初回アクセス時に、以下の手順でデータベースを接続します。

1. **データベースの種類**: `PostgreSQL` を選択。
2. **ホスト名**: `db` (Dockerネットワーク内のサービス名)
3. **データベース名 / ユーザー名 / パスワード**: `.env` で設定した値を入力。
4. **反映**: 保存後、テーブルが同期されるのを待ちます。

### SQLの登録
データが蓄積されたら、[分析・SQLガイド](./analytics/sql-guide.md) を参照して、提供されている16種類のクエリを登録してください。

## 🌐 5. 外部公開モード (オプション)

仲間にダッシュボードを公開したい場合は、以下のコマンドで起動します。
```bash
docker-compose --profile external up -d
```

起動後、管理画面または Discord Bot の /url コマンドで公開用URLを確認できます。

