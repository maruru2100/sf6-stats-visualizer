#!/usr/bin/env python3
"""Restore a zip produced by tools/migration/backup.py.

Safety design:
  - Every file in the archive is verified against the SHA256 recorded in
    manifest.json before anything is touched.
  - If the current environment already has data, --force is required.
  - Unless --skip-pre-backup is given, the current state is first exported
    with backup.py (--mode backup --no-secrets) into backups/, so a failed
    or mistaken restore can be rolled back.
  - Archive members are extracted with path-traversal protection.

Secret handling on restore is also option controlled:
  --include-secrets / --no-secrets   apply or skip both secret files
                                      (default: apply the ones in the archive)
  --no-env / --no-cookies            skip only that file

Other options:
  --force              allow overwriting existing DB / metabase-data
  --skip-pre-backup    do not export the current state first (not recommended)
  --no-start           restore data only, do not start services at the end
  --profile-external   also start the 'external' profile (tunnel, discord-bot)
  --dry-run            verify the archive, print the plan, touch nothing

Restore order matters: secrets (.env) and metabase-data are placed BEFORE
the database is started, so on a fresh PC PostgreSQL initialises with the
same credentials the dump was taken with.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("archive", type=Path, help="zip produced by backup.py")
    p.add_argument("--include-secrets", action="store_true",
                   help="apply secret files from the archive (this is the default)")
    p.add_argument("--no-secrets", action="store_true", help="skip .env and cookies")
    p.add_argument("--no-env", action="store_true", help="skip .env")
    p.add_argument("--no-cookies", action="store_true", help="skip the cookie file")
    p.add_argument("--force", action="store_true", help="overwrite existing data")
    p.add_argument("--skip-pre-backup", action="store_true")
    p.add_argument("--no-start", action="store_true")
    p.add_argument("--profile-external", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    return p


def verify_and_extract(archive: Path, dest: Path) -> dict:
    with zipfile.ZipFile(archive) as zf:
        bad = zf.testzip()
        if bad is not None:
            raise SystemExit(f"zip is corrupt at: {bad}")
        names = zf.namelist()
        if "manifest.json" not in names:
            raise SystemExit("manifest.json not found in archive (not a backup.py zip?)")
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        common.check_format_version(manifest)
        for info in zf.infolist():
            if info.is_dir():
                continue
            target = common.safe_join(dest, info.filename)
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
    # Verify hashes recorded in the manifest.
    for entry in manifest.get("files", []):
        path = dest / entry["path"]
        if not path.exists():
            raise SystemExit(f"file missing after extract: {entry['path']}")
        digest = common.sha256_file(path)
        if digest != entry["sha256"]:
            raise SystemExit(f"sha256 mismatch: {entry['path']}")
    return manifest


def wait_for_db(timeout_sec: int = 60) -> None:
    deadline = time.time() + timeout_sec
    remote = 'pg_isready -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-sf6_stats}"'
    while time.time() < deadline:
        result = common.compose("exec", "-T", "db", "sh", "-c", remote,
                                check=False, capture=True)
        if result.returncode == 0:
            return
        time.sleep(2)
    raise SystemExit("db did not become ready in time")


def check_http(url: str, tries: int = 15) -> bool:
    for _ in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:
                if resp.status < 500:
                    return True
        except Exception:
            time.sleep(2)
    return False


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.include_secrets and args.no_secrets:
        raise SystemExit("conflicting options: --include-secrets and --no-secrets")
    apply_secrets = not args.no_secrets
    apply_env = apply_secrets and not args.no_env
    apply_cookies = apply_secrets and not args.no_cookies

    archive = args.archive.resolve()
    if not archive.exists():
        raise SystemExit(f"archive not found: {archive}")

    root = common.REPO_ROOT
    (root / "backups").mkdir(parents=True, exist_ok=True)
    work_root = Path(tempfile.mkdtemp(prefix=".restore-", dir=str(root / "backups")))
    try:
        print("Verifying archive and checksums ...")
        manifest = verify_and_extract(archive, work_root)
        includes = manifest.get("includes", {})
        plan = {
            "archive": str(archive),
            "created_at": manifest.get("created_at"),
            "mode": manifest.get("mode"),
            "git_commit": manifest.get("git_commit"),
            "includes": includes,
            "apply_env": apply_env and bool(includes.get("secrets_env")),
            "apply_cookies": apply_cookies and bool(includes.get("secrets_cookies")),
            "table_counts_expected": manifest.get("table_counts", {}),
            "force": args.force,
            "pre_backup": not args.skip_pre_backup,
            "start_services": not args.no_start,
            "profile_external": args.profile_external,
        }
        print("Restore plan:")
        print(json.dumps(plan, indent=2, ensure_ascii=False))
        if args.dry_run:
            print("\n--dry-run: archive verified, nothing was changed.")
            return 0

        common.warn_if_not_repo_root()

        # --- Overwrite guard ---
        mb_dir = root / common.METABASE_DATA_DIR
        mb_has_data = mb_dir.exists() and any(mb_dir.iterdir())
        db_running = common.is_service_running("db")
        if (mb_has_data or db_running) and not args.force:
            raise SystemExit(
                "existing data was found (metabase-data and/or a running db). "
                "Re-run with --force to overwrite it."
            )

        # --- Pre-restore backup of the current state ---
        if not args.skip_pre_backup and (mb_has_data or db_running):
            print("\nExporting the current state first (pre-restore backup) ...")
            cmd = [sys.executable, str(Path(__file__).resolve().parent / "backup.py"),
                   "--mode", "backup", "--no-secrets"]
            if not db_running:
                cmd.append("--skip-db")
            if not mb_has_data:
                cmd.append("--skip-metabase")
            result = subprocess.run(cmd, cwd=str(root))
            if result.returncode != 0:
                raise SystemExit(
                    "pre-restore backup failed; aborting. "
                    "Fix it, or re-run with --skip-pre-backup if you accept the risk."
                )

        # --- Stop everything (volumes are kept) ---
        print("\nStopping services ...")
        common.compose("--profile", "external", "down", check=False)

        # --- Place files BEFORE db starts (fresh-PC credential order) ---
        if plan["apply_env"]:
            shutil.copy2(work_root / "secrets" / ".env", root / ".env")
            print("placed .env")
        if plan["apply_cookies"]:
            dest = root / common.SECRET_COOKIE_PATH
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(work_root / "secrets" / "local_cookies.json", dest)
            print("placed scraper/auth/local_cookies.json")
        if includes.get("metabase") and (work_root / "metabase-data").exists():
            if mb_dir.exists():
                shutil.rmtree(mb_dir)
            shutil.copytree(work_root / "metabase-data", mb_dir)
            print("placed metabase-data/")

        # --- Database ---
        if includes.get("db"):
            print("\nStarting db only ...")
            common.compose("up", "-d", "db")
            wait_for_db()
            dump = work_root / "db.dump"
            print("Restoring PostgreSQL (pg_restore --clean --if-exists) ...")
            remote = (
                'pg_restore --clean --if-exists --no-owner '
                '-U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-sf6_stats}"'
            )
            with open(dump, "rb") as f:
                result = common.compose("exec", "-T", "db", "sh", "-c", remote,
                                        check=False, stdin_file=f)
            if result.returncode != 0:
                print("warning: pg_restore returned non-zero. This is common with "
                      "--clean on a fresh database; verifying row counts next.")

            print("\nRunning flyway migrations (should be a no-op) ...")
            common.compose("up", "flyway", check=False)

            print("\nVerifying row counts against the manifest ...")
            actual = common.get_table_counts()
            expected = manifest.get("table_counts", {})
            mismatches = []
            for table, exp in expected.items():
                if exp is not None and actual.get(table) != exp:
                    mismatches.append(f"{table}: expected {exp}, got {actual.get(table)}")
            if mismatches:
                print("MISMATCH:\n  " + "\n  ".join(mismatches))
                raise SystemExit("row count verification failed")
            print(f"row counts OK: {json.dumps(actual, ensure_ascii=False)}")

        # --- Start services ---
        if not args.no_start:
            print("\nStarting services ...")
            up_args = ["up", "-d"]
            if args.profile_external:
                up_args = ["--profile", "external", "up", "-d"]
            common.compose(*up_args)
            if includes.get("metabase"):
                ok = check_http("http://localhost:3000/api/health")
                print(f"metabase /api/health: {'OK' if ok else 'not responding yet (check docker compose logs metabase)'}")
            ok = check_http("http://localhost:8000/health", tries=5)
            print(f"scraper /health: {'OK' if ok else 'not responding yet (check docker compose logs scraper)'}")
    finally:
        shutil.rmtree(work_root, ignore_errors=True)

    print("\nRestore finished.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
