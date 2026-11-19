"""Shared helpers for the SF6 migration / backup tools.

Standard library only, so the tools run on a fresh PC with just
Python 3 and Docker (Compose v2) installed.

Issue: #32 (migration tool)
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

FORMAT_VERSION = 1

# tools/migration/common.py -> repo root is two levels up.
REPO_ROOT = Path(__file__).resolve().parents[2]

# Tables whose row counts are recorded in the manifest and compared
# after a restore. Tables that do not exist yet are recorded as None.
COUNT_TABLES = [
    "battle_results",
    "player_stats",
    "target_users",
    "scraper_config",
    "system_status",
    "feature_requests",
    "flyway_schema_history",
]

SECRET_ENV_PATH = Path(".env")
SECRET_COOKIE_PATH = Path("scraper/auth/local_cookies.json")
METABASE_DATA_DIR = Path("metabase-data")
CONFIG_FILES = [Path("docker-compose.yml"), Path(".env.example")]


def eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


def run_cmd(
    cmd: list[str],
    *,
    check: bool = True,
    capture: bool = False,
    stdout_file=None,
    stdin_file=None,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess:
    """Run a command, echoing it first. Returns the CompletedProcess."""
    printable = " ".join(str(c) for c in cmd)
    print(f"+ {printable}")
    result = subprocess.run(
        [str(c) for c in cmd],
        cwd=str(cwd or REPO_ROOT),
        stdout=stdout_file if stdout_file is not None else (subprocess.PIPE if capture else None),
        stdin=stdin_file,
        text=False if stdout_file is not None or stdin_file is not None else True,
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"command failed ({result.returncode}): {printable}")
    return result


_compose_cmd_cache: list[str] | None = None


def compose_cmd() -> list[str]:
    """Return the Docker Compose command prefix ('docker compose' preferred)."""
    global _compose_cmd_cache
    if _compose_cmd_cache is not None:
        return _compose_cmd_cache
    for candidate in (["docker", "compose"], ["docker-compose"]):
        try:
            result = subprocess.run(
                candidate + ["version"], capture_output=True, text=True
            )
        except FileNotFoundError:
            continue
        if result.returncode == 0:
            _compose_cmd_cache = candidate
            return candidate
    raise RuntimeError(
        "Docker Compose was not found. Install Docker Desktop / Docker Engine "
        "with the Compose plugin and try again."
    )


def compose(*args: str, **kwargs) -> subprocess.CompletedProcess:
    return run_cmd(compose_cmd() + list(args), **kwargs)


def service_container_id(service: str) -> str:
    """Return the running container id for a compose service, or ''."""
    result = compose("ps", "-q", service, check=False, capture=True)
    out = (result.stdout or "").strip() if isinstance(result.stdout, str) else ""
    return out.splitlines()[0].strip() if out else ""


def is_service_running(service: str) -> bool:
    return bool(service_container_id(service))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_env_value(env_path: Path, key: str, default: str = "") -> str:
    """Read one KEY=value entry from a .env file (no shell expansion)."""
    if not env_path.exists():
        return default
    for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        if k.strip() == key:
            return v.strip().strip('"').strip("'")
    return default


def git_commit(repo_root: Path = REPO_ROOT) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except FileNotFoundError:
        pass
    return "unknown"


def get_table_counts() -> dict[str, int | None]:
    """Row counts for COUNT_TABLES via psql inside the db container.

    Returns None per table when the table does not exist or psql fails.
    The credentials are taken from the container's own environment
    (env_file: .env), so nothing secret is read on the host.
    """
    counts: dict[str, int | None] = {}
    for table in COUNT_TABLES:
        sql = f"SELECT count(*) FROM {table};"
        remote = (
            'psql -t -A -v ON_ERROR_STOP=1 '
            '-U "${POSTGRES_USER:-postgres}" '
            '-d "${POSTGRES_DB:-sf6_stats}" '
            f"-c \"{sql}\""
        )
        result = compose(
            "exec", "-T", "db", "sh", "-c", remote, check=False, capture=True
        )
        out = (result.stdout or "").strip() if isinstance(result.stdout, str) else ""
        try:
            counts[table] = int(out.splitlines()[0]) if result.returncode == 0 else None
        except (ValueError, IndexError):
            counts[table] = None
    return counts


def safe_join(base: Path, member_name: str) -> Path:
    """Join an archive member name under base, rejecting path traversal."""
    target = (base / member_name).resolve()
    base_resolved = base.resolve()
    if target != base_resolved and base_resolved not in target.parents:
        raise ValueError(f"unsafe path in archive: {member_name}")
    return target


def load_manifest_from_dir(path: Path) -> dict:
    manifest_path = path / "manifest.json"
    if not manifest_path.exists():
        raise ValueError("manifest.json not found in archive")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def check_format_version(manifest: dict) -> None:
    version = manifest.get("format_version")
    if version != FORMAT_VERSION:
        raise ValueError(
            f"unsupported backup format_version: {version!r} "
            f"(this tool supports {FORMAT_VERSION})"
        )


def running_under_repo_root() -> bool:
    return (REPO_ROOT / "docker-compose.yml").exists()


def warn_if_not_repo_root() -> None:
    if not running_under_repo_root():
        eprint(
            f"warning: docker-compose.yml not found under {REPO_ROOT}. "
            "Run the tool from inside the sf6-stats-visualizer repository."
        )


def env_or_os(name: str) -> str | None:
    value = os.environ.get(name)
    return value if value else None
