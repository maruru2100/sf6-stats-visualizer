"""Unit tests for tools/migration (standard library unittest only).

Run from the repository root:
    python -m unittest tools.migration.test_migration_tools
or:
    python tools/migration/test_migration_tools.py

These tests do not need Docker: they cover env parsing, hashing,
archive path safety, manifest handling and the --dry-run paths.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import merge as merge_tool  # noqa: E402

HERE = Path(__file__).resolve().parent


class TestCommon(unittest.TestCase):
    def test_sha256(self) -> None:
        self.assertEqual(
            common.sha256_bytes(b"abc"),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        )

    def test_safe_join_rejects_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            ok = common.safe_join(base, "sub/file.txt")
            self.assertTrue(str(ok).startswith(str(base.resolve())))
            with self.assertRaises(ValueError):
                common.safe_join(base, "../escape.txt")
            with self.assertRaises(ValueError):
                common.safe_join(base, "/etc/passwd")

    def test_check_format_version(self) -> None:
        common.check_format_version({"format_version": common.FORMAT_VERSION})
        with self.assertRaises(ValueError):
            common.check_format_version({"format_version": 999})


def make_sample_archive(
    path: Path,
    *,
    config_content: bytes = b"abc",
    includes_override: dict | None = None,
) -> None:
    """Write a minimal backup.py-style zip.

    The manifest always records the hash of b"abc"; pass a different
    config_content to simulate a tampered archive.
    """
    includes = {"db": False, "metabase": False, "config": True,
                "secrets_env": False, "secrets_cookies": False}
    includes.update(includes_override or {})
    manifest = {
        "format_version": common.FORMAT_VERSION,
        "tool": "test",
        "mode": "backup",
        "created_at": "2026-01-01T00:00:00+09:00",
        "git_commit": "deadbeef",
        "includes": includes,
        "table_counts": {},
        "files": [
            {"path": "config/docker-compose.yml", "size": 3,
             "sha256": common.sha256_bytes(b"abc")},
        ],
    }
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("config/docker-compose.yml", config_content)
        zf.writestr("manifest.json", json.dumps(manifest))


class TestDryRuns(unittest.TestCase):
    def test_backup_dry_run(self) -> None:
        result = subprocess.run(
            [sys.executable, str(HERE / "backup.py"), "--dry-run", "--no-secrets"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--dry-run: nothing was executed.", result.stdout)
        self.assertIn('"include_env": false', result.stdout)

    def test_backup_dry_run_excludes_secrets_by_default(self) -> None:
        result = subprocess.run(
            [sys.executable, str(HERE / "backup.py"), "--dry-run"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"mode": "backup"', result.stdout)
        self.assertIn('"include_env": false', result.stdout)
        self.assertIn('"include_cookies": false', result.stdout)

    def test_backup_dry_run_migration_mode_includes_secrets(self) -> None:
        result = subprocess.run(
            [sys.executable, str(HERE / "backup.py"), "--dry-run", "--mode", "migration"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"include_env": true', result.stdout)
        self.assertIn('"include_cookies": true', result.stdout)

    def test_restore_dry_run_verifies_sample_archive(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            archive = Path(td) / "sample.zip"
            make_sample_archive(archive)
            result = subprocess.run(
                [sys.executable, str(HERE / "restore.py"), str(archive), "--dry-run"],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("archive verified", result.stdout)

    def test_restore_rejects_tampered_archive(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            archive = Path(td) / "bad.zip"
            make_sample_archive(archive, config_content=b"tampered")
            result = subprocess.run(
                [sys.executable, str(HERE / "restore.py"), str(archive), "--dry-run"],
                capture_output=True, text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("sha256 mismatch", result.stderr)

    def test_restore_ignores_secret_flag_when_file_missing(self) -> None:
        # Manifest claims .env is included but the archive has no secrets/.env:
        # the plan must not try to apply it (would crash mid-restore).
        with tempfile.TemporaryDirectory() as td:
            archive = Path(td) / "no-secret-file.zip"
            make_sample_archive(archive, includes_override={"secrets_env": True})
            result = subprocess.run(
                [sys.executable, str(HERE / "restore.py"), str(archive), "--dry-run"],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('"apply_env": false', result.stdout)


def make_merge_archive(path: Path, *, dump_content: bytes = b"abc") -> None:
    """Write a minimal backup zip that includes a DB dump.

    The manifest records the hash of b"abc" for db.dump; pass a different
    dump_content to simulate a tampered archive.
    """
    manifest = {
        "format_version": common.FORMAT_VERSION,
        "tool": "test",
        "mode": "backup",
        "created_at": "2026-01-01T00:00:00+09:00",
        "git_commit": "deadbeef",
        "includes": {"db": True, "metabase": False, "config": False,
                     "secrets_env": False, "secrets_cookies": False},
        "table_counts": {},
        "files": [
            {"path": "db.dump", "size": 3,
             "sha256": common.sha256_bytes(b"abc")},
        ],
    }
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("db.dump", dump_content)
        zf.writestr("manifest.json", json.dumps(manifest))


class TestMerge(unittest.TestCase):
    def test_merge_table_policies(self) -> None:
        # Existing rows always win, and the decided scope is enforced.
        self.assertEqual(
            merge_tool.MERGE_TABLES["player_stats"], ("user_id", "recorded_at")
        )
        self.assertEqual(merge_tool.MERGE_TABLES["battle_results"], ("battle_id",))
        for skipped in ("feature_requests", "system_status", "flyway_schema_history"):
            self.assertNotIn(skipped, merge_tool.MERGE_TABLES)
            self.assertIn(skipped, merge_tool.SKIP_TABLES)

    def test_validate_db_name(self) -> None:
        self.assertEqual(
            merge_tool.validate_db_name("sf6_stats_merge_staging"),
            "sf6_stats_merge_staging",
        )
        for bad in ("a; DROP DATABASE x", "a b", "1abc", "a-b", ""):
            with self.assertRaises(ValueError):
                merge_tool.validate_db_name(bad)

    def test_build_insert_sql(self) -> None:
        sql = merge_tool.build_insert_sql(
            "battle_results", ["battle_id", "played_at"], ("battle_id",)
        )
        self.assertIn("INSERT INTO battle_results (battle_id, played_at)", sql)
        self.assertIn("ON CONFLICT (battle_id) DO NOTHING", sql)
        self.assertIn("battle_id IS NOT NULL", sql)

    def test_build_count_new_sql(self) -> None:
        sql = merge_tool.build_count_new_sql(
            "player_stats", ("user_id", "recorded_at")
        )
        self.assertIn("NOT EXISTS", sql)
        self.assertIn("t.user_id = s.user_id", sql)
        self.assertIn("t.recorded_at = s.recorded_at", sql)

    def test_build_merge_script_has_no_blank_line_before_eod(self) -> None:
        # A blank line between the CSV rows and "\." is read by COPY as a
        # one-field row and fails with "missing data for column".
        csv = b"u1,A\nu2,B\n"
        script = merge_tool.build_merge_script(
            "target_users", ["user_code", "player_name"], ("user_code",), csv
        )
        self.assertIn(
            b"\\copy merge_src (user_code, player_name) FROM STDIN WITH (FORMAT csv)\n"
            + csv + b"\\.\n",
            script,
        )
        self.assertNotIn(b"\n\n\\.", script)
        # An empty source table must also put "\." right after the \copy line.
        empty = merge_tool.build_merge_script(
            "target_users", ["user_code"], ("user_code",), b""
        )
        self.assertIn(b"FROM STDIN WITH (FORMAT csv)\n\\.\n", empty)

    def test_psql_handles_bytes_stdout(self) -> None:
        # psql() always feeds the script via stdin_file, which makes
        # common.run_cmd capture stdout as bytes rather than str.
        calls: list[list[str]] = []

        def fake_compose(*args, **kwargs):
            calls.append(list(args))
            return subprocess.CompletedProcess(
                args=list(args), returncode=0, stdout=b"8\n", stderr=None
            )

        original = merge_tool.common.compose
        merge_tool.common.compose = fake_compose
        try:
            self.assertEqual(merge_tool.flyway_version(None), "8")
            self.assertEqual(merge_tool.flyway_version(merge_tool.STAGING_DB), "8")
        finally:
            merge_tool.common.compose = original
        self.assertEqual(len(calls), 2)
        self.assertIn("-d sf6_stats_merge_staging", calls[1][-1])

    def test_table_columns_from_bytes_stdout(self) -> None:
        def fake_compose(*args, **kwargs):
            return subprocess.CompletedProcess(
                args=list(args), returncode=0,
                stdout=b"id\nuser_code\nplayer_name\n", stderr=None,
            )

        original = merge_tool.common.compose
        merge_tool.common.compose = fake_compose
        try:
            cols = merge_tool.table_columns(None, "target_users")
        finally:
            merge_tool.common.compose = original
        self.assertEqual(cols, ["id", "user_code", "player_name"])

    def test_merge_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            archive = Path(td) / "with-db.zip"
            make_merge_archive(archive)
            result = subprocess.run(
                [sys.executable, str(HERE / "merge.py"), str(archive), "--dry-run"],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Merge plan", result.stdout)
            self.assertIn("--dry-run: archive verified", result.stdout)

    def test_merge_rejects_archive_without_db(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            archive = Path(td) / "no-db.zip"
            make_sample_archive(archive)
            result = subprocess.run(
                [sys.executable, str(HERE / "merge.py"), str(archive), "--dry-run"],
                capture_output=True, text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("does not include a database dump", result.stderr)

    def test_merge_rejects_tampered_dump(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            archive = Path(td) / "tampered.zip"
            make_merge_archive(archive, dump_content=b"evil")
            result = subprocess.run(
                [sys.executable, str(HERE / "merge.py"), str(archive), "--dry-run"],
                capture_output=True, text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("sha256 mismatch", result.stderr)


if __name__ == "__main__":
    unittest.main()
