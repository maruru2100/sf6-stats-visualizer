# 変更履歴 (CHANGELOG)

このプロジェクトの主な変更を記録します。
形式は [Keep a Changelog](https://keepachangelog.com/ja/1.1.0/) に準拠し、
バージョニングは [セマンティック バージョニング](https://semver.org/lang/ja/) を使います。

- 変更はまず `Unreleased` に追記し、リリース時にバージョン節へ移します（手順は [docs/release.md](docs/release.md)）。
- 移行ツール (tools/migration) のバックアップ形式の版 (`format_version`) は、このバージョンとは別の独立した番号です。

## [Unreleased]

### Added
- 変更履歴 (CHANGELOG.md) とリリース手順 (docs/release.md) を導入。

## [0.1.0] - 2026-11-24

初回リリースとして、現行 main の状態に付けるベースライン。
（タグ `v0.1.0` は本変更のマージ後に付与する）

### Added
- Buckler's Booty のスクレイピング (Playwright): 戦績と PlayStats の自動取得、自動追従スキャン、強制スキャンモード、ページネーション不具合の修正
- 認証まわり: Cookie 期限切れの検知と通知、Chrome を使った認証 Cookie の更新 (auth_refresh)
- データ基盤: PostgreSQL + Flyway によるスキーマ管理 (V1〜V8)、分析用ビュー `v_battle_analytics`（名前変更対応の user_id 連携を含む）
- REST API: scraper に FastAPI を追加し、管理画面 (Streamlit) を API クライアントとして分離。Swagger の日本語説明と Authorize 対応
- Metabase 連携: 分析ダッシュボードと SQL 資産 (analytics/queries)、cloudflared トンネルによる外部公開、公開モードの `.env` 設定による自動判定 (#35)
- Discord Bot: `/scan_user` / `/scan_all` によるスキャン操作、`/info` コマンド、`/url` / `/update_url`、匿名の要望 (意見箱) 送信
- 管理画面: ターゲットユーザーの管理 (有効/無効、メモ)、実行ログとスクリーンショットの確認、要望管理
- 移行・バックアップツール (tools/migration): DB と Metabase データのバックアップ / リストア / PC 間移行 (#34)
- ドキュメント: GitHub Pages (セットアップ / 運用 / 分析SQL / 移行)

[Unreleased]: https://github.com/maruru2100/sf6-stats-visualizer/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/maruru2100/sf6-stats-visualizer/releases/tag/v0.1.0
