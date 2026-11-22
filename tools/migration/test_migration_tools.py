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


if __name__ == "__main__":
    unittest.main()
