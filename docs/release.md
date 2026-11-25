# 🏷️ リリース手順

バージョンの付け方と、リリース作業の手順です。変更履歴はリポジトリ直下の [CHANGELOG.md](https://github.com/maruru2100/sf6-stats-visualizer/blob/main/CHANGELOG.md) にあります。

## バージョニング (セマンティック バージョニング)

`vMAJOR.MINOR.PATCH`（例: `v0.1.0`）を使います。

| 桁 | 上げる条件 | 例 |
|---|---|---|
| MAJOR | 互換性を壊す変更 | DB スキーマの後方互換なし変更、`.env` 項目の削除・意味変更、移行ツールの前提変更 |
| MINOR | 後方互換のある機能追加 | 新しいコマンド / エンドポイント / 画面機能の追加 |
| PATCH | 後方互換のある修正 | バグ修正、ドキュメント整備、依存のマイナー更新 |

- 1.0.0 までは開発版として、MINOR で互換性の小さい変更を含むことがあります。
- Flyway のマイグレーション追加だけでは版は決めません。利用者への影響（既存 DB がそのまま使えるか）で判断します。
- 移行ツールのバックアップ形式の版 (`format_version`) は、このバージョンとは独立です。形式を変えたらそちらも上げます。

## 普段の作業

- 変更を含む PR では、`CHANGELOG.md` の `Unreleased` に1行追記します（Added / Changed / Fixed など）。
- 追記し忘れても、リリース時に PR 一覧から拾って補います。

## リリース作業

1. `CHANGELOG.md` を更新する PR を作る
   - `Unreleased` の内容を `## [X.Y.Z] - YYYY-MM-DD` 節へ移し、空の `Unreleased` を残す
   - ファイル末尾の比較リンクを新しいタグに合わせて更新する
2. PR を main にマージする
3. タグを付ける（どちらか）
   - GitHub の Releases 画面で「Draft a new release」→ タグ `vX.Y.Z` を main に対して新規作成（この方法だとタグと Release が同時にできる）
   - または手元で `git tag -a vX.Y.Z -m "vX.Y.Z" && git push origin vX.Y.Z`
4. GitHub Release の本文に、CHANGELOG の該当節を貼る
5. 必要なら移行ツールでリリース時点のバックアップを取る（`tools/migration`、モードは backup）

## 初回タグについて

- 初回は現行 main を `v0.1.0` とします（CHANGELOG 導入 PR のマージ後に付与）。
- それ以前の変更は CHANGELOG の `0.1.0` 節にまとめてあります。
