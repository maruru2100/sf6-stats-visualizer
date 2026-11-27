#!/usr/bin/env python3
"""Merge (differential insert) a backup.py zip into the running system.

Unlike restore.py (full replace), merge.py only inserts rows that the
target system does not have yet, keyed by each table's natural key.
Existing rows always win; nothing is updated or deleted. Use it to fold
data collected on another system (e.g. a second PC) into this one:

  1. On the other system:  backup.py            (produces a zip)
  2. On this system:       merge.py <that zip>

Policies (decided in Issue #44):
  - player_stats: the target (existing) rows win on (user_id, recorded_at)
  - feature_requests: not merged (no natural key to deduplicate by)
  - system_status:    not merged (instance-specific values, e.g. URL)
  - Metabase data:    not merged (cannot be combined at file level)

Safety design:
  - The archive is verified against the SHA256 in manifest.json before
    anything is touched (same check as restore.py).
  - Unless --skip-pre-backup is given, the current DB is first exported
    with backup.py (--mode backup --no-secrets --skip-metabase), so a
    mistaken merge can be rolled back with restore.py.
  - The dump is loaded into a throwaway staging database and merged from
    there; the staging database is always dropped afterwards.
  - If the Flyway schema versions of the two databases differ, the merge
    aborts before inserting anything.
  - The `id` (SERIAL) columns are never transferred: each system numbers
    its rows independently, so carrying ids over would collide. New rows
    get fresh ids from the target's own sequences.
  - Other services are never stopped or restarted; only the db service
    is started when it is not running yet.

Options:
  --dry-run            verify the archive, print the plan, touch nothing
  --skip-pre-backup    do not export the current DB first (not recommended)
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import restore as restore_tool  # noqa: E402  (reuse verify_and_extract / wait_for_db)

STAGING_DB = "sf6_stats_merge_staging"

# Tables merged by merge.py: table name -> natural-key (conflict) columns.
# Existing rows always win (ON CONFLICT ... DO NOTHING).
MERGE_TABLES: dict[str, tuple[str, ...]] = {
    "target_users": ("user_code",),
    "battle_results": ("battle_id",),
    "player_stats": ("user_id", "recorded_at"),
    "scraper_config": ("key",),
}

# Tables deliberately not merged (see the module docstring).
SKIP_TABLES = ("system_status", "feature_requests", "flyway_schema_history")

_DB_NAME_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("archive", type=Path, help="zip produced by backup.py")
    p.add_argument("--skip-pre-backup", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    return p


def validate_db_name(name: str) -> str:
    """Only allow plain identifiers: the name is embedded in SQL strings."""
    if not _DB_NAME_RE.match(name):
        raise ValueError(f"unsafe database name: {name!r}")
    return name


def build_copy_out_sql(table: str, columns: list[str]) -> str:
    cols = ", ".join(columns)
    return f"\\copy (SELECT {cols} FROM {table}) TO STDOUT WITH (FORMAT csv)"


def build_insert_sql(table: str, columns: list[str], conflict: tuple[str, ...]) -> str:
    """INSERT the staged rows, skipping conflicts; prints the inserted count."""
    cols = ", ".join(columns)
    not_null = " AND ".join(f"{c} IS NOT NULL" for c in conflict)
    return (
        f"WITH ins AS (INSERT INTO {table} ({cols}) "
        f"SELECT {cols} FROM merge_src WHERE {not_null} "
        f"ON CONFLICT ({', '.join(conflict)}) DO NOTHING RETURNING 1) "
        "SELECT count(*) FROM ins;"
    )


def build_count_new_sql(table: str, conflict: tuple[str, ...]) -> str:
    """Count staged rows whose natural key is not in the target table."""
    join = " AND ".join(f"t.{c} = s.{c}" for c in conflict)
    not_null = " AND ".join(f"s.{c} IS NOT NULL" for c in conflict)
    return (
        f"SELECT count(*) FROM merge_src s WHERE {not_null} "
        f"AND NOT EXISTS (SELECT 1 FROM {table} t WHERE {join});"
    )


def build_merge_script(
    table: str, columns: list[str], conflict: tuple[str, ...], csv_data: bytes
) -> bytes:
    """One psql script: temp table -> \\copy in -> count new -> insert.

    The CSV rows are inlined after the \\copy line and terminated by the
    end-of-data marker. COPY output already ends with a newline, so the
    marker must follow the data directly: a blank line in between would be
    read as a one-field row and fail with "missing data for column".
    """
    if csv_data and not csv_data.endswith(b"\n"):
        csv_data += b"\n"
    head = (
        f"CREATE TEMP TABLE merge_src AS SELECT * FROM {table} LIMIT 0;\n"
        f"\\copy merge_src ({', '.join(columns)}) FROM STDIN WITH (FORMAT csv)\n"
    )
    tail = (
        "\\.\n"
        + build_count_new_sql(table, conflict)
        + "\n"
        + build_insert_sql(table, columns, conflict)
        + "\n"
    )
    return head.encode("utf-8") + csv_data + tail.encode("utf-8")


def stdout_text(result: subprocess.CompletedProcess) -> str:
    """Captured stdout as str.

    common.run_cmd switches to binary mode whenever stdin_file is given
    (which psql() always does), so captured output arrives as bytes.
    """
    out = result.stdout
    if isinstance(out, bytes):
        out = out.decode("utf-8", errors="replace")
    return (out or "").strip()


def psql(
    sql: str,
    *,
    db: str | None = None,
    stdin_file: Path | None = None,
    stdout_file: Path | None = None,
    capture: bool = False,
) -> subprocess.CompletedProcess:
    """Run psql inside the db container, feeding it a script on stdin.

    db=None targets the application database via the container's own
    environment (${POSTGRES_DB:-sf6_stats}); an explicit name is used for
    the staging / maintenance databases and must be a plain identifier.
    """
    db_expr = validate_db_name(db) if db else '"${POSTGRES_DB:-sf6_stats}"'
    remote = (
        'psql -v ON_ERROR_STOP=1 -t -A '
        '-U "${POSTGRES_USER:-postgres}" '
        f"-d {db_expr}"
    )
    script = stdin_file
    tmp_path: Path | None = None
    if script is None:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".sql", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(sql)
            tmp_path = Path(tmp.name)
        script = tmp_path
    stdin_handle = script.open("rb")
    stdout_handle = stdout_file.open("wb") if stdout_file else None
    try:
        return common.compose(
            "exec", "-T", "db", "sh", "-c", remote,
            check=False, capture=capture,
            stdin_file=stdin_handle,
            stdout_file=stdout_handle,
        )
    finally:
        stdin_handle.close()
        if stdout_handle is not None:
            stdout_handle.close()
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


def psql_value(sql: str, *, db: str | None = None) -> str:
    result = psql(sql, db=db, capture=True)
    out = stdout_text(result)
    if result.returncode != 0:
        raise SystemExit(f"psql failed for: {sql}\n{out}")
    return out.splitlines()[0] if out else ""


def table_columns(db: str | None, table: str) -> list[str]:
    sql = (
        "SELECT column_name FROM information_schema.columns "
        f"WHERE table_schema = 'public' AND table_name = '{table}' "
        "ORDER BY ordinal_position;"
    )
    result = psql(sql, db=db, capture=True)
    out = stdout_text(result)
    if result.returncode != 0:
        raise SystemExit(f"could not read columns of {table}: {out}")
    return [line.strip() for line in out.splitlines() if line.strip()]


def flyway_version(db: str | None) -> str:
    return psql_value(
        "SELECT version FROM flyway_schema_history "
        "WHERE success ORDER BY installed_rank DESC LIMIT 1;",
        db=db,
    )


def drop_staging() -> None:
    psql(
        f'DROP DATABASE IF EXISTS {STAGING_DB} WITH (FORCE);',
        db="postgres",
    )


def merge_table(
    table: str,
    conflict: tuple[str, ...],
    work_root: Path,
) -> dict[str, int]:
    """Transfer one table from the staging DB into the target DB."""
    target_cols = [c for c in table_columns(None, table) if c != "id"]
    staging_cols = [c for c in table_columns(STAGING_DB, table) if c != "id"]
    if staging_cols != target_cols:
        raise SystemExit(
            f"column mismatch for {table}: staging {staging_cols} "
            f"vs target {target_cols}. Aborting (schema versions differ?)."
        )
    cols = target_cols

    csv_path = work_root / f"merge-{table}.csv"
    result = psql(
        build_copy_out_sql(table, cols), db=STAGING_DB, stdout_file=csv_path
    )
    if result.returncode != 0:
        raise SystemExit(f"export from staging failed for {table}")

    combined = work_root / f"merge-{table}.combined"
    combined.write_bytes(
        build_merge_script(table, cols, conflict, csv_path.read_bytes())
    )
    result = psql("", stdin_file=combined, capture=True)
    out = stdout_text(result)
    if result.returncode != 0:
        raise SystemExit(f"merge insert failed for {table}: {out}")
    numbers = [int(line) for line in out.splitlines() if line.strip().isdigit()]
    if len(numbers) != 2:
        raise SystemExit(f"unexpected psql output for {table}: {out!r}")
    new_count, inserted = numbers
    staged = int(psql_value(f"SELECT count(*) FROM {table};", db=STAGING_DB))
    return {"staged": staged, "new": new_count, "inserted": inserted,
            "skipped": staged - inserted}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    archive = args.archive.resolve()
    if not archive.exists():
        raise SystemExit(f"archive not found: {archive}")

    root = common.REPO_ROOT
    if args.dry_run:
        work_root = Path(tempfile.mkdtemp(prefix="sf6-merge-"))
    else:
        (root / "backups").mkdir(parents=True, exist_ok=True)
        work_root = Path(tempfile.mkdtemp(prefix=".merge-", dir=str(root / "backups")))
    staging_created = False
    try:
        print("Verifying archive and checksums ...")
        manifest = restore_tool.verify_and_extract(archive, work_root)
        if not (work_root / "db.dump").is_file():
            raise SystemExit(
                "this archive does not include a database dump (db.dump). "
                "Create it with backup.py without --skip-db."
            )
        plan = {
            "archive": str(archive),
            "created_at": manifest.get("created_at"),
            "mode": manifest.get("mode"),
            "git_commit": manifest.get("git_commit"),
            "merge_tables": {t: list(c) for t, c in MERGE_TABLES.items()},
            "skip_tables": list(SKIP_TABLES),
            "pre_backup": not args.skip_pre_backup,
        }
        print("Merge plan (existing rows always win):")
        print(json.dumps(plan, indent=2, ensure_ascii=False))
        if args.dry_run:
            print("\n--dry-run: archive verified, nothing was changed.")
            return 0

        common.warn_if_not_repo_root()

        # --- Make sure the db is up (start only the db service) ---
        db_running = common.is_service_running("db")
        db_has_volume = common.db_volume_exists()
        if not db_running:
            print("\nStarting db only ...")
            common.compose("up", "-d", "db")
            restore_tool.wait_for_db()

        # --- Pre-merge backup of the current state ---
        if not args.skip_pre_backup and (db_running or db_has_volume):
            print("\nExporting the current DB first (pre-merge backup) ...")
            cmd = [sys.executable,
                   str(Path(__file__).resolve().parent / "backup.py"),
                   "--mode", "backup", "--no-secrets", "--skip-metabase"]
            result = subprocess.run(cmd, cwd=str(root))
            if result.returncode != 0:
                raise SystemExit(
                    "pre-merge backup failed; aborting. "
                    "Fix it, or re-run with --skip-pre-backup if you accept the risk."
                )

        # --- Schema must exist on the target ---
        if not table_columns(None, "battle_results"):
            print("\nTarget tables not found; running flyway migrations ...")
            common.compose("up", "flyway", check=False)
            if not table_columns(None, "battle_results"):
                raise SystemExit("target tables still missing after flyway; aborting.")

        counts_before = common.get_table_counts()

        # --- Load the dump into the staging database ---
        print(f"\nLoading dump into staging database ({STAGING_DB}) ...")
        drop_staging()
        psql(f"CREATE DATABASE {STAGING_DB};", db="postgres")
        staging_created = True
        remote = (
            'pg_restore --no-owner -U "${POSTGRES_USER:-postgres}" '
            f"-d {STAGING_DB}"
        )
        with open(work_root / "db.dump", "rb") as f:
            result = common.compose(
                "exec", "-T", "db", "sh", "-c", remote,
                check=False, stdin_file=f, capture_stderr=True,
            )
        if result.returncode != 0:
            err = restore_tool.stderr_text(result).strip()
            raise SystemExit(
                "pg_restore into the staging database failed"
                + (f":\n{err}" if err else ".")
            )

        # --- Flyway schema versions must match ---
        target_version = flyway_version(None)
        staging_version = flyway_version(STAGING_DB)
        print(f"flyway versions: target={target_version} source={staging_version}")
        if target_version != staging_version:
            raise SystemExit(
                "flyway schema versions differ; refusing to merge. "
                "Update both systems to the same version first."
            )

        # --- Merge table by table ---
        print("\nMerging ...")
        summary: dict[str, dict[str, int]] = {}
        for table, conflict in MERGE_TABLES.items():
            summary[table] = merge_table(table, conflict, work_root)
            s = summary[table]
            print(f"  {table}: staged {s['staged']}, "
                  f"inserted {s['inserted']}, skipped {s['skipped']}")

        counts_after = common.get_table_counts()
        print("\nRow counts (before -> after):")
        for table in MERGE_TABLES:
            print(f"  {table}: {counts_before.get(table)} -> {counts_after.get(table)}")
    finally:
        if staging_created:
            drop_staging()
        shutil.rmtree(work_root, ignore_errors=True)

    print("\nMerge finished.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
