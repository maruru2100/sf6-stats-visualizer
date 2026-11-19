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

HERE = Path(__file__).resolve().parent


class TestCommon(unittest.TestCase):
    def test_read_env_value(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            env = Path(td) / ".env"
            env.write_text(
                "# comment\nPOSTGRES_DB=sf6_stats\nQUOTED='x y'\nEMPTY=\n",
                encoding="utf-8",
            )
            self.assertEqual(common.read_env_value(env, "POSTGRES_DB"), "sf6_stats")
            self.assertEqual(common.read_env_value(env, "QUOTED"), "x y")
            self.assertEqual(common.read_env_value(env, "MISSING", "dflt"), "dflt")
            self.assertEqual(common.read_env_value(Path(td) / "nope", "X", "d"), "d")

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


def make_sample_archive(path: Path) -> None:
    manifest = {
        "format_version": common.FORMAT_VERSION,
        "tool": "test",
        "mode": "backup",
        "created_at": "2026-01-01T00:00:00+09:00",
        "git_commit": "deadbeef",
        "includes": {"db": False, "metabase": False, "config": True,
                     "secrets_env": False, "secrets_cookies": False},
        "table_counts": {},
        "files": [
            {"path": "config/docker-compose.yml", "size": 3,
             "sha256": common.sha256_bytes(b"abc")},
        ],
    }
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("config/docker-compose.yml", b"abc")
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

    def test_backup_dry_run_migration_includes_secrets_by_default(self) -> None:
        result = subprocess.run(
            [sys.executable, str(HERE / "backup.py"), "--dry-run"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"include_env": true', result.stdout)

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
            make_sample_archive(archive)
            with zipfile.ZipFile(archive, "a") as zf:
                zf.writestr("config/docker-compose.yml", b"tampered")
            result = subprocess.run(
                [sys.executable, str(HERE / "restore.py"), str(archive), "--dry-run"],
                capture_output=True, text=True,
            )
            self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
