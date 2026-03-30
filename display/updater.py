"""Self-update system — check for and install updates via git.

All git operations use subprocess with timeouts to avoid hanging.
The install step does NOT restart services — the caller handles that.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

log = logging.getLogger("voxel.updater")

# Repository root (two levels up from this file: display/updater.py -> voxel/)
_REPO_ROOT = str(Path(__file__).resolve().parent.parent)

# Default timeout for git operations (seconds)
_GIT_TIMEOUT = 30


def _run_git(*args: str, timeout: int = _GIT_TIMEOUT) -> subprocess.CompletedProcess:
    """Run a git command in the repo root with timeout."""
    cmd = ["git", "-C", _REPO_ROOT, *args]
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout,
    )


def _load_update_config() -> dict:
    """Load update settings from config."""
    try:
        from config.settings import load_settings
        settings = load_settings()
        return settings.get("updates", {})
    except Exception:
        return {}


def get_current_version() -> str:
    """Get current version from pyproject.toml, falling back to git short hash."""
    # Try pyproject.toml first
    try:
        toml_path = Path(_REPO_ROOT) / "pyproject.toml"
        if toml_path.exists():
            for line in toml_path.read_text().splitlines():
                if line.strip().startswith("version"):
                    # version = "0.1.0"
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass

    # Fall back to git short hash
    try:
        result = _run_git("rev-parse", "--short", "HEAD", timeout=10)
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass

    return "unknown"


def check_for_update() -> dict:
    """Check if updates are available.

    Returns:
        {
            available: bool,
            current: str,       # short commit hash
            latest: str,        # short commit hash of remote
            behind: int,        # number of commits behind
            changelog: list[str],  # recent commit messages (max 10)
            error: str,         # empty if no error
        }
    """
    cfg = _load_update_config()
    remote = cfg.get("repo", "origin")
    branch = cfg.get("channel", "main")

    result = {
        "available": False,
        "current": "",
        "latest": "",
        "behind": 0,
        "changelog": [],
        "error": "",
    }

    try:
        # Fetch latest from remote
        fetch = _run_git("fetch", remote, branch, timeout=30)
        if fetch.returncode != 0:
            result["error"] = f"Fetch failed: {fetch.stderr.strip()}"
            return result

        # Current commit
        current = _run_git("rev-parse", "--short", "HEAD", timeout=10)
        if current.returncode != 0:
            result["error"] = "Failed to get current commit"
            return result
        result["current"] = current.stdout.strip()

        # Latest commit on remote branch
        remote_ref = f"{remote}/{branch}"
        latest = _run_git("rev-parse", "--short", remote_ref, timeout=10)
        if latest.returncode != 0:
            result["error"] = f"Failed to get latest commit for {remote_ref}"
            return result
        result["latest"] = latest.stdout.strip()

        # How many commits behind
        behind = _run_git(
            "rev-list", "--count", f"HEAD..{remote_ref}", timeout=10,
        )
        if behind.returncode == 0:
            result["behind"] = int(behind.stdout.strip())

        # Changelog (max 10 lines)
        if result["behind"] > 0:
            changelog = _run_git(
                "log", "--oneline", f"HEAD..{remote_ref}", "-n", "10",
                timeout=10,
            )
            if changelog.returncode == 0:
                result["changelog"] = [
                    line.strip()
                    for line in changelog.stdout.strip().splitlines()
                    if line.strip()
                ]

        result["available"] = result["behind"] > 0
        log.info(
            f"Update check: current={result['current']} latest={result['latest']} "
            f"behind={result['behind']}"
        )

    except subprocess.TimeoutExpired:
        result["error"] = "Git operation timed out"
        log.warning("Update check timed out")
    except Exception as e:
        result["error"] = str(e)
        log.warning(f"Update check failed: {e}")

    return result


def install_update() -> dict:
    """Pull latest code and sync dependencies.

    Returns:
        {
            ok: bool,
            old_version: str,
            new_version: str,
            error: str,
        }
    """
    cfg = _load_update_config()
    remote = cfg.get("repo", "origin")
    branch = cfg.get("channel", "main")

    result = {
        "ok": False,
        "old_version": "",
        "new_version": "",
        "error": "",
    }

    try:
        # Record old version
        old = _run_git("rev-parse", "--short", "HEAD", timeout=10)
        result["old_version"] = old.stdout.strip() if old.returncode == 0 else "unknown"

        # Stash any local changes
        stash = _run_git("stash", timeout=10)
        stashed = stash.returncode == 0 and "No local changes" not in stash.stdout

        # Pull latest
        pull = _run_git("pull", remote, branch, timeout=60)
        if pull.returncode != 0:
            # Try to restore stash on failure
            if stashed:
                _run_git("stash", "pop", timeout=10)
            result["error"] = f"Pull failed: {pull.stderr.strip()}"
            return result

        # Sync Python dependencies
        try:
            from hw.detect import IS_PI
        except ImportError:
            IS_PI = False

        sync_cmd = ["uv", "sync"]
        if IS_PI:
            sync_cmd.extend(["--extra", "pi"])

        sync = subprocess.run(
            sync_cmd, capture_output=True, text=True, timeout=120,
            cwd=_REPO_ROOT,
        )
        if sync.returncode != 0:
            log.warning(f"Dependency sync had issues: {sync.stderr.strip()}")
            # Non-fatal — the pull succeeded

        # Record new version
        new = _run_git("rev-parse", "--short", "HEAD", timeout=10)
        result["new_version"] = new.stdout.strip() if new.returncode == 0 else "unknown"

        result["ok"] = True
        log.info(f"Update installed: {result['old_version']} -> {result['new_version']}")

    except subprocess.TimeoutExpired:
        result["error"] = "Operation timed out"
        log.error("Update install timed out")
    except Exception as e:
        result["error"] = str(e)
        log.error(f"Update install failed: {e}")

    return result
