# 移行・バックアップツール（Issue #32）

別PCの Docker 環境へ移行する時と、日常のバックアップ用に、Git 管理外のデータを
1つの zip にまとめ／戻すためのツールです。Python 標準ライブラリのみで動作します。

## 移行対象

コード、`docker-compose.yml`、`flyway/sql` は Git にあるので対象外です。
対象は Git に入っていない次のデータだけです。

| 対象 | 内容 | 方式 |
|---|---|---|
| PostgreSQL (`sf6_stats`) | 戦績・統計・ユーザー・要望・公開URL・Flyway履歴 | コンテナ内で `pg_dump -Fc`（オンライン取得） |
| `metabase-data/` | Metabase のダッシュボード／カード／ユーザー／DB接続設定（H2） | metabase を一時停止してフォルダごとコピー |
| `docker-compose.yml`、`.env.example` | 構成の記録 | `config/` にコピー |
| `.env`（秘密） | DBパスワード、Discord／Cloudflare トークン等 | オプションで制御（下記） |
| `scraper/auth/local_cookies.json`（秘密） | Buckler's の Cookie | オプションで制御（下記） |

zip 内には `manifest.json` が入り、作成日時・Gitコミット・モード・各テーブルの件数・
全ファイルの SHA256 が記録されます。リストア時はチェックサムと件数で検証します。

## 秘密情報の制御（起動オプション）

秘密ファイル（`.env` と Cookie）は、バックアップ／リストアとも起動オプションで制御します。

### バックアップ側（backup.py）

| 指定 | `.env` | Cookie |
|---|---|---|
| `--mode backup`（デフォルト） | 含まない | 含まない |
| `--mode migration` | 含む | 含む |
| `--include-secrets` / `--no-secrets` | モードのプリセットを上書き（両方） | 同左 |
| `--include-env` / `--no-env` | 個別に上書き | － |
| `--include-cookies` / `--no-cookies` | － | 個別に上書き |

明示フラグが常に `--mode` のプリセットより優先されます。
秘密を含む zip は「読める人＝全ての秘密を読める人」です。保管・受け渡しに注意してください。

### リストア側（restore.py）

デフォルトはアーカイブ内の秘密をそのまま適用します。
`--no-secrets`（両方）、`--no-env`、`--no-cookies` で個別に止められます。

## 使い方

前提： リポジトリのルートで実行すること。Docker Compose が使えること。

### バックアップ／移行用エクスポート

```bat
rem 日常バックアップ用（秘密を含まない・デフォルト）
tools\migration\backup.bat

rem 移行用（秘密を含む）
tools\migration\backup.bat --mode migration

rem 何が起きるかだけ確認
tools\migration\backup.bat --mode migration --dry-run
```

Linux では `tools/migration/backup.sh` が同じ引数で使えます。
出力先はデフォルトで `backups/sf6-<mode>-YYYYMMDD-HHMMSS.zip` です
（`backups/` は `.gitignore` 済み）。

### リストア

```bat
rem まず検証だけ
tools\migration\restore.bat backups\sf6-migration-20260101-120000.zip --dry-run

rem 本番リストア（既存データがある場合は --force が必須）
tools\migration\restore.bat backups\sf6-migration-20260101-120000.zip --force
```

安全策：

- チェックサムが1つでも合わなければ何も変更せず終了します
- 既存データ（`metabase-data/`、起動中の db、または停止中でも `postgres_data` ボリューム）が
  あるのに `--force` が無ければ終了します
- `--force` 時も、リストア前に現在の状態を `backups/` へ自動エクスポートします
  （秘密なし・モード backup）。db が停止中でもボリュームがあれば一時的に起動して
  ダンプを取ります。止めたい場合だけ `--skip-pre-backup`
- アーカイブに秘密ファイルが実際に入っている場合だけ適用します
  （manifest のフラグではなくファイルの有無で判定）
- リストア順序は「秘密と metabase-data を配置 → db 起動 → `pg_restore --clean --if-exists`
  → flyway（通常は no-op）→ 件数検証 → サービス起動」です。
  新規PCで `.env` の認証情報で PostgreSQL が初期化されるよう、この順序にしています
- 外部公開モード（tunnel / discord-bot）も起動したい場合は `--profile-external`

Linux での注意： metabase コンテナが書き込んだ `metabase-data/` は別ユーザー所有になることがあり、
リストア時の削除／上書きで `Permission denied` になる場合があります。その場合は
`sudo chown -R $USER metabase-data` してから再実行するか、`sudo` 付きで実行してください。

### 別PCへの移行手順

1. 移行元で `backup.bat --mode migration`（秘密を含む移行モード）を実行し、zip を移行先へ渡す
2. 移行先でリポジトリを clone し、Docker を入れる
3. zip を `backups/` に置き、`restore.bat <zip> --force` を実行する
   （新規PCでは既存データが無いため、本来 `--force` は不要だが、metabase-data の
   プレースホルダ等がある環境では必要になる場合がある）
4. `docker compose --profile external up -d` で外部公開モードも使う場合は起動する
5. Metabase（http://localhost:3000）と管理画面（http://localhost:8501）を開いて確認する

注意： 既存PCで動いている PostgreSQL ボリュームは、`.env` の `POSTGRES_PASSWORD` を
後から変えてもパスワードは変わりません（初期化時の値が volume 内に残ります）。
パスワードごと変えたい場合は、リストアではなく volume の作り直しが必要です。

## テスト

Docker 不要の単体テスト（チェックサム、パストラバーサル防止、
`--dry-run`、改ざん検知、秘密ファイル欠落時の扱い）:

```bat
python tools\migration\test_migration_tools.py
```

## 今回の範囲外（Phase 2 候補）

- PostgreSQL ボリューム丸ごとの物理コピー（`--full-volume`）
- アーカイブの暗号化
- 定期バックアップのスケジュール実行
