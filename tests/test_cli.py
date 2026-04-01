"""CLI smoke tests — verify commands exit cleanly and produce expected output.

Uses subprocess to invoke the real CLI via `python -m cli <command>`.
These are integration tests that validate argument parsing and basic execution.

NOTE: cli.app imports cli.display which replaces sys.stdout/sys.stderr on
Windows (for UTF-8 support with Rich). This breaks pytest's capture mechanism
when cli.app is imported in-process. All parser tests therefore use subprocess
to evaluate parser behavior in an isolated process.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest


# ── Helpers ─────────────────────────────────────────────────────────────────


def _run_cli(*args: str, timeout: float = 30) -> subprocess.CompletedProcess:
    """Run a voxel CLI command via python -m cli and return the result."""
    cmd = [sys.executable, "-m", "cli", *args]
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        cmd,
        capture_output=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
        env=env,
    )


def _run_python(code: str, timeout: float = 15) -> subprocess.CompletedProcess:
    """Run a Python snippet in a subprocess and return the result."""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
        env=env,
    )


# ── 1. voxel version ───────────────────────────────────────────────────────


def test_version_exits_zero():
    """'voxel version' should exit 0."""
    result = _run_cli("version")
    assert result.returncode == 0


def test_version_contains_version_string():
    """'voxel version' output should contain a version number."""
    result = _run_cli("version")
    output = result.stdout + result.stderr
    # Version is either from importlib.metadata or fallback "0.1.0-dev"
    assert any(c.isdigit() for c in output), f"Expected version digits in output: {output[:200]}"


# ── 2. voxel doctor ────────────────────────────────────────────────────────


def test_doctor_completes_successfully():
    """'voxel doctor' should complete without crashing (exit 0 or small N for issues found)."""
    result = _run_cli("doctor")
    # doctor returns the number of failures found, so exit 0 = no issues,
    # exit 1-5 = some issues (normal on desktop without gateway, ffmpeg, etc.)
    # A crash would show a traceback and likely exit > 10 or negative.
    assert 0 <= result.returncode <= 10, (
        f"doctor appears to have crashed (exit {result.returncode}): {result.stderr[:500]}"
    )
    output = result.stdout + result.stderr
    assert len(output) > 50, "Expected diagnostic output from doctor"


# ── 3. voxel config ────────────────────────────────────────────────────────


def test_config_exits_zero():
    """'voxel config' (no subcommand) should exit 0 and show config."""
    result = _run_cli("config")
    assert result.returncode == 0
    output = result.stdout + result.stderr
    # Config output should contain YAML-like content
    assert len(output) > 10, f"Expected config output, got: {output[:200]}"


def test_config_get_known_key():
    """'voxel config get gateway.url' should exit 0 or 1 (key may not exist)."""
    result = _run_cli("config", "get", "gateway.url")
    # Even if the value is empty/default, it should not crash
    assert result.returncode in (0, 1), f"config get crashed: {result.stderr[:500]}"


# ── 4. voxel --all ──────────────────────────────────────────────────────────


def test_all_flag_shows_commands():
    """'voxel --all' should show commands including experimental ones."""
    result = _run_cli("--all")
    assert result.returncode == 0
    output = result.stdout + result.stderr
    assert len(output) > 0, "Expected some output from --all"


# ── 5. voxel (no command) ──────────────────────────────────────────────────


def test_no_command_shows_help():
    """'voxel' with no command should exit 0 and show available commands."""
    result = _run_cli()
    assert result.returncode == 0
    output = result.stdout + result.stderr
    # Should show command list
    assert len(output) > 0, "Expected help output with no command"


# ── 6. voxel nonexistent-command ────────────────────────────────────────────


def test_unknown_command_exits_nonzero():
    """'voxel nonexistent-command' should exit non-zero (argparse error)."""
    result = _run_cli("nonexistent-command-xyz")
    # argparse treats unrecognized arguments as an error (exit code 2)
    assert result.returncode != 0


# ── 7. Build parser tests (subprocess) ─────────────────────────────────────
#
# These tests evaluate cli.app.build_parser() in an isolated subprocess to
# avoid the sys.stdout/stderr replacement issue on Windows.


def test_build_parser_has_expected_commands():
    """build_parser() should define all expected subcommands."""
    code = """
import json
from cli.app import build_parser
parser = build_parser()
for action in parser._subparsers._actions:
    if hasattr(action, '_parser_class'):
        print(json.dumps(sorted(action.choices.keys())))
        break
"""
    result = _run_python(code)
    assert result.returncode == 0, f"Script failed: {result.stderr[:300]}"

    commands = json.loads(result.stdout.strip())
    expected = {"doctor", "version", "config", "status", "start", "stop",
                "restart", "logs", "setup", "build", "update", "hw",
                "uninstall", "mcp", "dev-push", "dev-pair", "backup"}

    actual = set(commands)
    missing = expected - actual
    assert not missing, f"Missing subcommands: {missing}"


def test_build_parser_version_no_args():
    """Parsing 'version' should set command='version'."""
    code = """
from cli.app import build_parser
parser = build_parser()
args = parser.parse_args(['version'])
print(args.command)
"""
    result = _run_python(code)
    assert result.returncode == 0
    assert result.stdout.strip() == "version"


def test_build_parser_config_set():
    """Parsing 'config set gateway.token abc' should set correct args."""
    code = """
import json
from cli.app import build_parser
parser = build_parser()
args = parser.parse_args(['config', 'set', 'gateway.token', 'abc123'])
print(json.dumps({
    'command': args.command,
    'config_command': args.config_command,
    'key': args.key,
    'value': args.value,
}))
"""
    result = _run_python(code)
    assert result.returncode == 0
    data = json.loads(result.stdout.strip())
    assert data["command"] == "config"
    assert data["config_command"] == "set"
    assert data["key"] == "gateway.token"
    assert data["value"] == "abc123"


def test_build_parser_config_get():
    """Parsing 'config get gateway.url' should set correct args."""
    code = """
import json
from cli.app import build_parser
parser = build_parser()
args = parser.parse_args(['config', 'get', 'gateway.url'])
print(json.dumps({
    'command': args.command,
    'config_command': args.config_command,
    'key': args.key,
}))
"""
    result = _run_python(code)
    assert result.returncode == 0
    data = json.loads(result.stdout.strip())
    assert data["command"] == "config"
    assert data["config_command"] == "get"
    assert data["key"] == "gateway.url"


def test_build_parser_dev_push_flags():
    """dev-push should accept --watch, --logs, --update flags."""
    code = """
import json
from cli.app import build_parser
parser = build_parser()
args = parser.parse_args(['dev-push', '--watch', '--logs', '--update'])
print(json.dumps({
    'command': args.command,
    'watch': args.watch,
    'logs': args.logs,
    'update': args.update,
}))
"""
    result = _run_python(code)
    assert result.returncode == 0
    data = json.loads(result.stdout.strip())
    assert data["command"] == "dev-push"
    assert data["watch"] is True
    assert data["logs"] is True
    assert data["update"] is True


def test_build_parser_mcp_defaults():
    """mcp subcommand should have correct defaults."""
    code = """
import json
from cli.app import build_parser
parser = build_parser()
args = parser.parse_args(['mcp'])
print(json.dumps({
    'command': args.command,
    'transport': args.transport,
    'port': args.port,
}))
"""
    result = _run_python(code)
    assert result.returncode == 0
    data = json.loads(result.stdout.strip())
    assert data["command"] == "mcp"
    assert data["transport"] == "sse"
    assert data["port"] == 8082


def test_build_parser_all_flag():
    """--all flag should be parsed at the top level."""
    code = """
import json
from cli.app import build_parser
parser = build_parser()
args = parser.parse_args(['--all'])
print(json.dumps({
    'all': args.all,
    'command': args.command,
}))
"""
    result = _run_python(code)
    assert result.returncode == 0
    data = json.loads(result.stdout.strip())
    assert data["all"] is True
    assert data["command"] is None


# ── 8. COMMANDS dispatch table ──────────────────────────────────────────────


def test_commands_dict_matches_parser():
    """Every subcommand in build_parser should have an entry in COMMANDS."""
    code = """
import json
from cli.app import build_parser, COMMANDS
parser = build_parser()
for action in parser._subparsers._actions:
    if hasattr(action, '_parser_class'):
        parser_cmds = sorted(action.choices.keys())
        break
else:
    parser_cmds = []
dict_cmds = sorted(COMMANDS.keys())
missing = sorted(set(parser_cmds) - set(dict_cmds))
print(json.dumps({'missing': missing}))
"""
    result = _run_python(code)
    assert result.returncode == 0
    data = json.loads(result.stdout.strip())
    assert data["missing"] == [], f"Subcommands missing from COMMANDS: {data['missing']}"


def test_get_version_returns_string():
    """_get_version() should return a non-empty string."""
    code = """
from cli.app import _get_version
v = _get_version()
print(v)
"""
    result = _run_python(code)
    assert result.returncode == 0
    version = result.stdout.strip()
    assert len(version) > 0, "Expected non-empty version string"
    assert isinstance(version, str)


# ── 9. CLI help text ────────────────────────────────────────────────────────


def test_help_flag():
    """'voxel --help' should exit 0 and show usage."""
    result = _run_cli("--help")
    assert result.returncode == 0
    output = result.stdout + result.stderr
    assert "voxel" in output.lower()


def test_doctor_help():
    """'voxel doctor --help' should exit 0."""
    result = _run_cli("doctor", "--help")
    assert result.returncode == 0
