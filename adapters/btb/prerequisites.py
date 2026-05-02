"""Pre-flight checks and auto-setup for BTB adapter commands.

Called by run_adapter and generate_smoke_test before their main logic.
Each check is idempotent: skips instantly when the prerequisite is already met,
runs the fix when it isn't.
"""

from __future__ import annotations

import logging
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

from .config import (
    DEFAULT_DATA_DIR,
    DEFAULT_SHARED_DIR,
    REPO_ROOT,
    REQUIRED_TOOLS,
    resolve_repo_path,
)

log = logging.getLogger("btb.prereq")

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

# Paths (resolved against repo root)
SHARED_DIR = resolve_repo_path(DEFAULT_SHARED_DIR)
_DEFAULT_DATA_DIR = resolve_repo_path(DEFAULT_DATA_DIR)
TEMPLATE_TEST_SH = REPO_ROOT / "adapters" / "btb" / "template" / "tests" / "test.sh"
SMOKE_TEST_SH = REPO_ROOT / "datasets" / "btb-smoke" / "btb-smoke" / "tests" / "test.sh"

HF_DOWNLOAD_SCRIPT = REPO_ROOT / "scripts" / "download_from_hf.py"


class PrerequisiteError(SystemExit):
    """Raised when a prerequisite cannot be auto-fixed (needs user action)."""

    def __init__(self, message: str) -> None:
        super().__init__(1)
        self.message = message


def _fail(message: str) -> None:
    """Print an actionable error and exit."""
    print(f"\n{'=' * 60}", file=sys.stderr)
    print("PREREQUISITE MISSING", file=sys.stderr)
    print(f"{'=' * 60}", file=sys.stderr)
    print(message, file=sys.stderr)
    print(f"{'=' * 60}\n", file=sys.stderr)
    raise PrerequisiteError(message)


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def ensure_hf_access() -> None:
    """Verify a HuggingFace token is available (env var or cached file)."""
    if os.environ.get("HF_TOKEN"):
        log.debug("HF_TOKEN env var found")
        return
    cached = Path.home() / ".cache" / "huggingface" / "token"
    if cached.exists() and cached.read_text().strip():
        log.debug("HF token found at %s", cached)
        return
    _fail(
        "HuggingFace token not found.\n\n"
        "Either:\n"
        "  1. Set the HF_TOKEN environment variable, or\n"
        "  2. Run: hf auth login\n"
    )


def _run_hf_download(*extra_args: str) -> None:
    """Run the HF download script with optional extra arguments."""
    if not HF_DOWNLOAD_SCRIPT.exists():
        _fail(f"Download script not found: {HF_DOWNLOAD_SCRIPT}")
    try:
        subprocess.run(
            [sys.executable, str(HF_DOWNLOAD_SCRIPT), *extra_args],
            check=True,
            cwd=str(REPO_ROOT),
        )
    except subprocess.CalledProcessError:
        _fail(
            "HuggingFace download failed.\n\n"
            "Try running manually:\n"
            f"  python {HF_DOWNLOAD_SCRIPT.relative_to(REPO_ROOT)}"
        )


def ensure_tool_data() -> None:
    """Ensure shared MCP tool data (VDR, SEC EDGAR, logos) is downloaded.

    Checks for shared/tools/ with a subdirectory per REQUIRED_TOOLS.
    Runs scripts/download_from_hf.py if missing.
    """
    dataset_dir = SHARED_DIR / "tools"
    missing = [t for t in REQUIRED_TOOLS if not (dataset_dir / t).is_dir()]

    if not missing:
        log.debug("Shared tool data OK (%s)", dataset_dir)
        return

    log.info("Shared tool data missing (%s), downloading...", ", ".join(missing))
    ensure_hf_access()
    _run_hf_download()

    # Verify after download
    still_missing = [t for t in REQUIRED_TOOLS if not (dataset_dir / t).is_dir()]
    if still_missing:
        _fail(
            f"Tool data download completed but still missing: {', '.join(still_missing)}\n"
            f"Expected at: {dataset_dir}"
        )
    log.info("Shared tool data downloaded successfully")


def ensure_task_data(data_dir: Path) -> None:
    """Ensure tasks.jsonl and task-data/ are populated under data_dir.

    If both exist, returns immediately without touching HuggingFace. If either
    is missing and data_dir is the HF default, downloads from HuggingFace. If
    either is missing and data_dir is custom, fails with a clear error.
    """
    json_path = data_dir / "tasks.jsonl"
    task_data_dir = data_dir / "task-data"

    json_ok = json_path.exists()
    data_ok = (
        task_data_dir.is_dir()
        and any(d.is_dir() and _UUID_RE.match(d.name) for d in task_data_dir.iterdir())
    )

    if json_ok and data_ok:
        log.debug("tasks.jsonl and task-data OK (%s)", data_dir)
        return

    if data_dir.resolve() != _DEFAULT_DATA_DIR:
        missing = []
        if not json_ok:
            missing.append(f"tasks JSON not found: {json_path}")
        if not data_ok:
            missing.append(f"task-data missing or empty: {task_data_dir}")
        _fail("\n".join(missing))

    reasons = []
    if not json_ok:
        reasons.append("tasks.jsonl missing")
    if not data_ok:
        reasons.append("task-data missing or empty")
    log.info("%s — downloading from HuggingFace...", ", ".join(reasons))
    ensure_hf_access()
    _run_hf_download("--skip-shared-tools")
    log.info("Task data download complete")


def ensure_test_sh_executable() -> None:
    """Ensure test.sh scripts have the execute bit set."""
    for path in (TEMPLATE_TEST_SH, SMOKE_TEST_SH):
        if not path.exists():
            continue
        if os.access(path, os.X_OK):
            continue
        current = path.stat().st_mode
        path.chmod(current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        log.info("Fixed permissions: chmod +x %s", path.relative_to(REPO_ROOT))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def ensure_all(*, data_dir: Path | None = None) -> None:
    """Run all prerequisite checks. Skips what's already done, fixes what it can.

    Args:
        data_dir: Root data directory containing tasks.jsonl and task-data/.
                  When None, task data checks are skipped (smoke test).
                  HF access is only required if a download is actually needed.
    """
    _setup_logging()

    log.info("Checking prerequisites...")

    ensure_tool_data()

    if data_dir is not None:
        ensure_task_data(data_dir)

    ensure_test_sh_executable()

    log.info("All prerequisites OK")


def _setup_logging() -> None:
    """Configure logging if not already configured by the caller."""
    if not logging.root.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)-7s %(message)s",
            datefmt="%H:%M:%S",
        )
    if log.level == logging.NOTSET:
        log.setLevel(logging.INFO)
