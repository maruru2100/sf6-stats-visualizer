# SF6 Stats Visualizer アーキテクチャドキュメント

## 1. プロジェクト概要
SF6統計可視化ツールのフルスタックアプリケーション。データ収集(REST API)・管理画面・DB(PostgreSQL + Flyway)・分析(Metabase)・通知(Discord Bot)で構成され、すべて `docker-compose.yml` で起動します。

## 2. モジュール構成
### 2.1 データ収集層 (scraper/ = バックエンド REST API)
- **役割**: ゲームデータのスクレイピング、定期実行、ユーザー/要望管理を REST API で提供
- **技術スタック**: Python / FastAPI / Playwright
- **主要ファイル**:
  - `scraper/api.py`: FastAPI 本体（エンドポイント、API キー認証）
  - `scraper/services.py`: ビジネスロジック（ユーザー、スケジュール、巡回ジョブ。同時実行は1本に制限）
  - `scraper/scheduler.py`: 定期巡回スレッド
  - `scraper/scraper.py`: スクレイピング処理
  - `scraper/auth_refresh.py`: 認証(クッキー)更新処理
  - `scraper/auth/`: 認証情報の配置先（cookie 等。git 管理対象外）
  - `scraper/config.py`: 環境変数の検証・基本設定
  - `scraper/logger.py`: ログ出力
  - `scraper/database.py`: データベース接続処理
  - `scraper/Dockerfile`: コンテナ化設定
- **主なエンドポイント**: `/health`, `/users`, `/scrape/*`, `/schedule`, `/logs`, `/system/*`（公開URL更新・スクリーンショット）, `/feature-requests`

### 2.1a データベース (db / flyway/)
- **役割**: PostgreSQL 15 (`db`)。スキーマは Flyway (`flyway/sql/V*.sql`) で管理し、起動時に自動マイグレーション
- **主なテーブル/ビュー**: `battle_results`, `player_stats`, `scraper_config`, `target_users`, `system_status`, `feature_requests`, ビュー `v_battle_analytics`

### 2.1b 管理画面 (frontend/)
- **役割**: Streamlit の管理画面。DB へは直接接続せず、`API_URL` の REST API のみを呼ぶ
- **主要ファイル**: `frontend/main.py`

### 2.2 分析層 (analytics/)
- **役割**: 収集データの分析とダッシュボード構築（Metabase、ポート3000。データは `metabase-data/`、git 管理対象外）
- **構成**:
  - `analytics/dashboards/`: 可視化用ダッシュボード（現状は空）
  - `analytics/queries/`: 分析クエリ定義（`01_`〜`16_` の連番SQL）
- **外部公開**: `tunnel` (cloudflared, profile `external`) で Metabase を公開

### 2.3 通知層 (discord_bot/)
- **役割**: Discord からの操作・通知（scraper の REST API 呼び出し、DB 参照）。profile `external` で起動
- **技術スタック**: Python + discord.py
- **主要ファイル**:
  - `discord_bot/bot.py`: ボット処理ロジック
  - `discord_bot/shared/`: `scraper/` をコンテナ内 `/app/shared` にマウントして `database.py` 等を共有

## 3. 技術スタック
| レイヤー | 使用技術 |
|---------|---------|
| データ収集 / API | Python, FastAPI, Playwright |
| 管理画面 | Python, Streamlit |
| DB | PostgreSQL 15, Flyway 10 |
| 分析 | Metabase |
| 通知 | Python, discord.py |
| デプロイ | Docker, docker-compose, cloudflared |

## 4. 特記事項
- 環境変数管理: `.env.example` をベースに `.env` を作成
- コンテナ構成: `docker-compose.yml` で定義（db, flyway, scraper:8000, frontend:8501, metabase:3000, tunnel/discord-bot は profile `external`）
- 起動順: db → flyway(マイグレーション完了) → scraper → frontend
- セキュリティ: `.gitignore` による不要ファイル排除、LICENSEファイルによるライセンス管理
- バージョン管理: Git で管理。ブランチ運用は `.github/agents/dev-verify.agent.md` を参照