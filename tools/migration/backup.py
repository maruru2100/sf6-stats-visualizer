#!/usr/bin/env python3
"""Back up / export the SF6 Stats Visualizer state as a single zip.

What is collected (see docs/migration.md):
  - PostgreSQL database   : pg_dump custom format (db.dump), taken online
                            via `docker compose exec db pg_dump`
  - Metabase application  : the whole ./metabase-data directory (H2 file).
    data                    The metabase container is stopped while copying
                            and started again afterwards.
  - Config                : docker-compose.yml and .env.example
  - Secrets (optional)    : .env and scraper/auth/local_cookies.json

Secret handling is controlled by command line options (Issue #32):
  --mode migration   preset: secrets INCLUDED (a migration needs them)
  --mode backup      preset: secrets EXCLUDED (routine backup)
  --include-secrets / --no-secrets        override the preset for both files
  --include-env / --no-env                override for .env only
  --include-cookies / --no-cookies        override for the cookie file only
Explicit flags always win over the --mode preset.

Other options:
  --output-dir DIR   where to write the zip (default: backups/)
  --output-file NAME zip file name (default: sf6-backup-YYYYMMDD-HHMMSS.zip)
  --skip-db          do not dump PostgreSQL
  --skip-metabase    do not copy metabase-data
  --dry-run          print the resolved plan and exit, touching nothing

Standard library only. Requires Docker Compose and a running db service
(unless --skip-db / --dry-run).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402


def resolve_flag(mode_default: bool, include: bool, exclude: bool) -> bool:
    if include and exclude:
        raise SystemExit("conflicting options: use only one of the include/no- pair")
    if include:
        return True
    if exclude:
        return False
    return mode_default


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--mode", choices=["migration", "backup"], default="migration",
                   help="preset: migration includes secrets, backup excludes them (default: migration)")
    p.add_argument("--include-secrets", action="store_true", help="include .env and cookies")
    p.add_argument("--no-secrets", action="store_true", help="exclude .env and cookies")
    p.add_argument("--include-env", action="store_true", help="include .env")
    p.add_argument("--no-env", action="store_true", help="exclude .env")
    p.add_argument("--include-cookies", action="store_true", help="include scraper/auth/local_cookies.json")
    p.add_argument("--no-cookies", action="store_true", help="exclude the cookie file")
    p.add_argument("--output-dir", type=Path, default=common.REPO_ROOT / "backups")
    p.add_argument("--output-file", type=str, default=None)
    p.add_argument("--skip-db", action="store_true")
    p.add_argument("--skip-metabase", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    mode_includes_secrets = args.mode == "migration"
    group = resolve_flag(mode_includes_secrets, args.include_secrets, args.no_secrets)
    include_env = resolve_flag(group, args.include_env, args.no_env)
    include_cookies = resolve_flag(group, args.include_cookies, args.no_cookies)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_name = args.output_file or f"sf6-{args.mode}-{timestamp}.zip"
    out_path = (args.output_dir / out_name).resolve()

    plan = {
        "mode": args.mode,
        "archive": str(out_path),
        "include_db": not args.skip_db,
        "include_metabase": not args.skip_metabase,
        "include_env": include_env,
        "include_cookies": include_cookies,
        "repo_root": str(common.REPO_ROOT),
    }
    print("Backup plan:")
    print(json.dumps(plan, indent=2, ensure_ascii=False))
    if include_env or include_cookies:
        print(
            "\nWARNING: this archive will contain secret files "
            f"(.env: {include_env}, cookies: {include_cookies}).\n"
            "Anyone who can read the zip can read those secrets. "
            "Store and transfer it accordingly."
        )
    if args.dry_run:
        print("\n--dry-run: nothing was executed.")
        return 0

    common.warn_if_not_repo_root()
    root = common.REPO_ROOT
    args.output_dir.mkdir(parents=True, exist_ok=True)

    staging_root = Path(tempfile.mkdtemp(prefix=".staging-", dir=str(args.output_dir)))
    staging = staging_root / "payload"
    staging.mkdir()
    manifest: dict = {
        "format_version": common.FORMAT_VERSION,
        "tool": "tools/migration/backup.py",
        "mode": args.mode,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "git_commit": common.git_commit(),
        "includes": {
            "db": not args.skip_db,
            "metabase": not args.skip_metabase,
            "config": True,
            "secrets_env": include_env,
            "secrets_cookies": include_cookies,
        },
        "table_counts": {},
        "files": [],
    }

    metabase_was_running = False
    try:
        # --- PostgreSQL (online dump) ---
        if not args.skip_db:
            if not common.is_service_running("db"):
                raise SystemExit(
                    "the db service is not running. Start it first: docker compose up -d db"
                )
            print("\nCollecting table counts ...")
            manifest["table_counts"] = common.get_table_counts()
            dump_path = staging / "db.dump"
            print("Dumping PostgreSQL (pg_dump -Fc) ...")
            remote = (
                'pg_dump -Fc -U "${POSTGRES_USER:-postgres}" '
                '-d "${POSTGRES_DB:-sf6_stats}"'
            )
            with open(dump_path, "wb") as f:
                result = common.compose(
                    "exec", "-T", "db", "sh", "-c", remote,
                    check=False, stdout_file=f,
                )
            if result.returncode != 0 or dump_path.stat().st_size == 0:
                raise SystemExit("pg_dump failed or produced an empty file")

        # --- Metabase (stop, copy, restart) ---
        if not args.skip_metabase:
            mb_dir = root / common.METABASE_DATA_DIR
            if mb_dir.exists():
                metabase_was_running = common.is_service_running("metabase")
                if metabase_was_running:
                    print("\nStopping metabase while copying its H2 data ...")
                    common.compose("stop", "metabase")
                try:
                    shutil.copytree(mb_dir, staging / "metabase-data")
                finally:
                    if metabase_was_running:
                        print("Starting metabase again ...")
                        common.compose("up", "-d", "metabase")
                        metabase_was_running = False
            else:
                print("\nmetabase-data/ does not exist, skipping it.")

        # --- Config (non-secret) ---
        config_dir = staging / "config"
        config_dir.mkdir(exist_ok=True)
        for rel in common.CONFIG_FILES:
            src = root / rel
            if src.exists():
                shutil.copy2(src, config_dir / rel.name)

        # --- Secrets (option controlled) ---
        secrets_dir = staging / "secrets"
        if include_env:
            src = root / common.SECRET_ENV_PATH
            if src.exists():
                secrets_dir.mkdir(exist_ok=True)
                shutil.copy2(src, secrets_dir / ".env")
            else:
                print("note: .env not found, nothing to include for --include-env")
        if include_cookies:
            src = root / common.SECRET_COOKIE_PATH
            if src.exists():
                secrets_dir.mkdir(exist_ok=True)
                shutil.copy2(src, secrets_dir / "local_cookies.json")
            else:
                print("note: cookie file not found, nothing to include for --include-cookies")

        # --- Manifest (hashes of every payload file) ---
        for file in sorted(staging.rglob("*")):
            if file.is_file():
                manifest["files"].append(
                    {
                        "path": file.relative_to(staging).as_posix(),
                        "size": file.stat().st_size,
                        "sha256": common.sha256_file(file),
                    }
                )
        (staging / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        # --- Zip it up and verify ---
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file in sorted(staging.rglob("*")):
                if file.is_file():
                    zf.write(file, file.relative_to(staging).as_posix())
        with zipfile.ZipFile(out_path) as zf:
            bad = zf.testzip()
            if bad is not None:
                raise SystemExit(f"zip verification failed at: {bad}")
    finally:
        if metabase_was_running:
            # Safety net if something failed between stop and the restart above.
            try:
                common.compose("up", "-d", "metabase")
            except Exception:
                pass
        shutil.rmtree(staging_root, ignore_errors=True)

    size_mb = out_path.stat().st_size / (1024 * 1024)
    print(f"\nDone: {out_path} ({size_mb:.1f} MiB)")
    print(f"Table counts: {json.dumps(manifest['table_counts'], ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
