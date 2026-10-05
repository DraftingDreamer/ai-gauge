#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Start a packaged GUI in an isolated profile and verify its startup log."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import tomllib


STARTUP_MARKERS = (
    " starting platform=",
    "hydrated cookies for: none",
    "heartbeat enabled interval_s=",
)
ERROR_MARKERS = (
    "dll load failed",
    "the specified procedure could not be found",
    "could not load the qt platform plugin",
    "could not find the qt platform plugin",
    "no qt platform plugin could be initialized",
    "could not initialize glx",
    "could not initialize egl",
    "failed to create opengl context",
    "qt.qpa.plugin",
    "failed to initialize",
    "could not initialize",
)


def resolve_gui_executable(value: str | Path, *, platform: str | None = None) -> Path:
    """Resolve an executable inside a platform bundle, including macOS .app."""
    platform = platform or sys.platform
    path = Path(value).expanduser().resolve()
    if path.suffix.lower() == ".app":
        path = path / "Contents" / "MacOS" / "ai-gauge"
    elif path.is_dir():
        path = path / ("ai-gauge.exe" if platform == "win32" else "ai-gauge")
    if not path.is_file():
        raise FileNotFoundError(f"packaged GUI executable not found: {path}")
    return path


def isolated_child_environment(root: Path, base: dict[str, str] | None = None) -> dict[str, str]:
    """Redirect app data, OS profiles, and all outbound proxy traffic."""
    env = dict(os.environ if base is None else base)
    env.update(
        {
            "APPDATA": str(root / "Roaming"),
            "LOCALAPPDATA": str(root / "Local"),
            "USERPROFILE": str(root / "User"),
            "HOME": str(root / "Home"),
            "XDG_CONFIG_HOME": str(root / ".config"),
            "HTTP_PROXY": "http://127.0.0.1:9",
            "HTTPS_PROXY": "http://127.0.0.1:9",
            "ALL_PROXY": "http://127.0.0.1:9",
            "http_proxy": "http://127.0.0.1:9",
            "https_proxy": "http://127.0.0.1:9",
            "all_proxy": "http://127.0.0.1:9",
            "NO_PROXY": "localhost,127.0.0.1,::1",
            "no_proxy": "localhost,127.0.0.1,::1",
            "QT_QPA_PLATFORM": "offscreen",
        }
    )
    return env


def isolated_config() -> dict[str, object]:
    """Config values that prevent providers, background work, or notices."""
    return {
        "start_at_login": False,
        "providers": {
            "claude": False,
            "codex": False,
            "copilot": False,
            "openrouter": False,
            "antigravity": False,
            "codex_resets": False,
            "claude_resets": False,
            "opencode_go": False,
        },
        "browser_accounts": [],
        "browser_accounts_version": 2,
        "mcp_enabled": False,
        "local_usage": {
            "enabled": False,
            "claude": {"enabled": False},
            "codex": {"enabled": False},
        },
        "codex_resets": {
            "notify_announced": False,
            "notify_landed": False,
            "notify_banked": False,
        },
        "claude_resets": {
            "notify_announced": False,
            "notify_landed": False,
            "notify_banked": False,
        },
    }


def find_startup_error(text: str) -> str | None:
    lowered = text.lower()
    for marker in ERROR_MARKERS:
        index = lowered.find(marker)
        if index >= 0:
            start = max(0, text.rfind("\n", 0, index) + 1)
            end = text.find("\n", index)
            return text[start : len(text) if end < 0 else end].strip()
    return None


def startup_line(text: str) -> str:
    return next(
        (line for line in text.splitlines() if " starting platform=" in line),
        "",
    )


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def expected_project_version() -> str:
    project_file = Path(__file__).resolve().parents[1] / "pyproject.toml"
    with project_file.open("rb") as source:
        return str(tomllib.load(source)["project"]["version"])


def wait_for_startup(
    log_path: Path,
    stderr_path: Path,
    process: subprocess.Popen[bytes],
    timeout: float,
    expected_version: str,
) -> str:
    deadline = time.monotonic() + timeout
    last_text = ""
    while time.monotonic() < deadline:
        last_text = _read(log_path) + "\n" + _read(stderr_path)
        error = find_startup_error(last_text)
        if error:
            raise RuntimeError(f"GUI startup reported a Qt/DLL initialization error: {error}")
        if all(marker in last_text for marker in STARTUP_MARKERS):
            startup = startup_line(last_text)
            expected_token = f"ai-gauge {expected_version} starting platform="
            if expected_token not in startup or "frozen=True" not in startup:
                raise RuntimeError(
                    "GUI startup log did not identify the expected frozen build "
                    f"version {expected_version!r}: {startup!r}"
                )
            if process.poll() is not None:
                raise RuntimeError(f"GUI exited after startup markers (exit={process.returncode}).\n{last_text}")
            return last_text
        if process.poll() is not None:
            raise RuntimeError(f"GUI exited before startup completed (exit={process.returncode}).\n{last_text}")
        time.sleep(0.25)
    raise TimeoutError(f"GUI startup markers were not logged within {timeout:g}s.\n{last_text}")


def terminate_owned_child(process: subprocess.Popen[bytes], timeout: float = 10) -> None:
    """Stop only the Popen child created by this smoke test."""
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=timeout)
    if process.poll() is None:
        raise RuntimeError("owned GUI process did not exit after terminate/kill")


def smoke_test(
    executable: Path,
    *,
    startup_timeout: float = 30,
    stability_seconds: float = 2,
) -> dict[str, str]:
    with tempfile.TemporaryDirectory(prefix="ai-gauge-gui-smoke-") as temporary:
        root = Path(temporary)
        env = isolated_child_environment(root)
        for variable in ("APPDATA", "LOCALAPPDATA", "USERPROFILE", "HOME", "XDG_CONFIG_HOME"):
            Path(env[variable]).mkdir(parents=True, exist_ok=True)
        # Platform.app_data_dir() intentionally honors APPDATA on every OS;
        # this matches the application's config.py/platforms/base.py paths.
        config_dir = Path(env["APPDATA"]) / "ai-gauge"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.json").write_text(
            json.dumps(isolated_config(), indent=2), encoding="utf-8"
        )
        log_path = config_dir / "ai-gauge.log"
        stdout_path = root / "stdout.log"
        stderr_path = root / "stderr.log"
        process: subprocess.Popen[bytes] | None = None
        startup_evidence = ""
        heartbeat_evidence = ""
        owned_pid = "unknown"
        try:
            with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
                process = subprocess.Popen(
                    [str(executable)],
                    cwd=str(executable.parent),
                    env=env,
                    stdin=subprocess.DEVNULL,
                    stdout=stdout,
                    stderr=stderr,
                )
            owned_pid = str(process.pid)
            startup_text = wait_for_startup(
                log_path,
                stderr_path,
                process,
                startup_timeout,
                expected_project_version(),
            )
            startup_evidence = startup_line(startup_text)
            heartbeat_evidence = next(
                line for line in startup_text.splitlines() if "heartbeat enabled interval_s=" in line
            )
            time.sleep(stability_seconds)
            stable_text = _read(log_path) + "\n" + _read(stderr_path)
            error = find_startup_error(stable_text)
            if error:
                raise RuntimeError(f"GUI reported a delayed Qt/DLL initialization error: {error}")
            if process.poll() is not None:
                raise RuntimeError(
                    f"GUI process exited during stability window (exit={process.returncode}).\n"
                    f"{_read(log_path)}\n{_read(stderr_path)}"
                )
        finally:
            if process is not None:
                terminate_owned_child(process)
        if process.poll() is None:
            raise RuntimeError("owned GUI process remained alive after cleanup")
        return {
            "startup": startup_evidence,
            "heartbeat": heartbeat_evidence,
            "owned_pid": owned_pid,
            "cleanup": "owned child terminated and exited",
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", help="one-folder bundle, macOS .app, or GUI executable")
    parser.add_argument("--timeout", type=float, default=30, help="startup wait in seconds")
    parser.add_argument("--stability", type=float, default=2, help="post-startup live window in seconds")
    args = parser.parse_args()
    executable = resolve_gui_executable(args.bundle)
    evidence = smoke_test(executable, startup_timeout=args.timeout, stability_seconds=args.stability)
    print(f"Packaged GUI startup smoke passed: {executable}")
    print(f"Startup: {evidence['startup']}")
    print(f"Heartbeat: {evidence['heartbeat']}")
    print(f"Cleanup: PID {evidence['owned_pid']} {evidence['cleanup']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
