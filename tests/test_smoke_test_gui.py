from __future__ import annotations

from pathlib import Path
import subprocess
from unittest.mock import Mock

import pytest

from tools import smoke_test_gui


def test_resolve_gui_executable_uses_macos_bundle_binary_directly(tmp_path):
    bundle = tmp_path / "ai-gauge.app"
    executable = bundle / "Contents" / "MacOS" / "ai-gauge"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"binary")

    assert smoke_test_gui.resolve_gui_executable(bundle, platform="darwin") == executable


def test_resolve_gui_executable_uses_windows_bundle_entry(tmp_path):
    bundle = tmp_path / "ai-gauge"
    executable = bundle / "ai-gauge.exe"
    bundle.mkdir()
    executable.write_bytes(b"binary")

    assert smoke_test_gui.resolve_gui_executable(bundle, platform="win32") == executable


def test_resolve_gui_executable_fails_closed_for_missing_bundle(tmp_path):
    with pytest.raises(FileNotFoundError, match="packaged GUI executable not found"):
        smoke_test_gui.resolve_gui_executable(tmp_path / "missing", platform="linux")


def test_child_environment_redirects_every_profile_and_closes_network(tmp_path):
    env = smoke_test_gui.isolated_child_environment(
        tmp_path,
        {
            "APPDATA": "real-appdata",
            "LOCALAPPDATA": "real-local-appdata",
            "USERPROFILE": "real-user-profile",
            "HOME": "real-home",
            "XDG_CONFIG_HOME": "real-xdg",
            "PATH": "preserved-runtime-path",
        },
    )

    assert env["APPDATA"] == str(tmp_path / "Roaming")
    assert env["LOCALAPPDATA"] == str(tmp_path / "Local")
    assert env["USERPROFILE"] == str(tmp_path / "User")
    assert env["HOME"] == str(tmp_path / "Home")
    assert env["XDG_CONFIG_HOME"] == str(tmp_path / ".config")
    assert env["PATH"] == "preserved-runtime-path"
    assert env["HTTPS_PROXY"] == "http://127.0.0.1:9"
    assert env["https_proxy"] == env["HTTPS_PROXY"]
    assert env["NO_PROXY"] == "localhost,127.0.0.1,::1"
    assert env["QT_QPA_PLATFORM"] == "offscreen"


def test_isolated_config_disables_providers_storage_notifications_and_autostart():
    config = smoke_test_gui.isolated_config()

    assert config["start_at_login"] is False
    assert all(config["providers"].values()) is False
    assert config["browser_accounts"] == []
    assert config["browser_accounts_version"] == 2
    assert config["mcp_enabled"] is False
    assert config["local_usage"] == {
        "enabled": False,
        "claude": {"enabled": False},
        "codex": {"enabled": False},
    }
    for provider in ("codex_resets", "claude_resets"):
        assert config[provider] == {
            "notify_announced": False,
            "notify_landed": False,
            "notify_banked": False,
        }


def test_startup_log_requires_expected_frozen_version_and_heartbeat(tmp_path):
    log_path = tmp_path / "ai-gauge.log"
    stderr_path = tmp_path / "stderr.log"
    log_path.write_text(
        "2026 [INFO] aigauge.app: ai-gauge 0.9.0 starting platform=linux "
        "frozen=True executable=/bundle cwd=/bundle app_data=/isolated\n"
        "hydrated cookies for: none\n"
        "heartbeat enabled interval_s=300\n",
        encoding="utf-8",
    )
    process = Mock()
    process.poll.return_value = None

    text = smoke_test_gui.wait_for_startup(
        log_path, stderr_path, process, 0.1, "0.9.0"
    )

    assert "heartbeat enabled interval_s=300" in text


def test_startup_log_rejects_wrong_version(tmp_path):
    log_path = tmp_path / "ai-gauge.log"
    stderr_path = tmp_path / "stderr.log"
    log_path.write_text(
        "ai-gauge 0.8.4 starting platform=linux frozen=False\n"
        "hydrated cookies for: none\nheartbeat enabled interval_s=300\n",
        encoding="utf-8",
    )
    process = Mock()
    process.poll.return_value = None

    with pytest.raises(RuntimeError, match="expected frozen build version"):
        smoke_test_gui.wait_for_startup(log_path, stderr_path, process, 0.1, "0.9.0")


def test_startup_log_rejects_version_prefix_collision(tmp_path):
    log_path = tmp_path / "ai-gauge.log"
    stderr_path = tmp_path / "stderr.log"
    log_path.write_text(
        "ai-gauge 0.9.01 starting platform=linux frozen=True\n"
        "hydrated cookies for: none\nheartbeat enabled interval_s=300\n",
        encoding="utf-8",
    )
    process = Mock()
    process.poll.return_value = None

    with pytest.raises(RuntimeError, match="expected frozen build version"):
        smoke_test_gui.wait_for_startup(log_path, stderr_path, process, 0.1, "0.9.0")


def test_startup_log_rejects_matching_version_when_not_frozen(tmp_path):
    log_path = tmp_path / "ai-gauge.log"
    stderr_path = tmp_path / "stderr.log"
    log_path.write_text(
        "ai-gauge 0.9.0 starting platform=linux frozen=False\n"
        "hydrated cookies for: none\nheartbeat enabled interval_s=300\n",
        encoding="utf-8",
    )
    process = Mock()
    process.poll.return_value = None

    with pytest.raises(RuntimeError, match="expected frozen build version"):
        smoke_test_gui.wait_for_startup(log_path, stderr_path, process, 0.1, "0.9.0")


@pytest.mark.parametrize(
    "diagnostic",
    [
        "QtCore.dll: The specified procedure could not be found",
        "qt.qpa.plugin: Could not load the Qt platform plugin \"offscreen\"",
        "Could not find the Qt platform plugin \"xcb\" in the plugin paths",
        "This application failed to start because no Qt platform plugin could be initialized",
        "ImportError: DLL load failed while importing QtCore",
    ],
)
def test_smoke_rejects_qt_and_native_dll_startup_errors(diagnostic):
    assert smoke_test_gui.find_startup_error(diagnostic) == diagnostic


def test_terminate_owned_child_only_signals_the_given_process():
    process = Mock()
    process.poll.side_effect = [None, 0]
    process.wait.return_value = 0

    smoke_test_gui.terminate_owned_child(process)

    process.terminate.assert_called_once_with()
    process.wait.assert_called_once_with(timeout=10)
    process.kill.assert_not_called()


def test_already_exited_child_is_not_signaled_again():
    process = Mock()
    process.poll.return_value = 3

    smoke_test_gui.terminate_owned_child(process)

    process.terminate.assert_not_called()
    process.kill.assert_not_called()
