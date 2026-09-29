import json
import subprocess
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QFileDialog

from aigauge.config import Config
from aigauge.models import SnapshotStatus
from aigauge.providers import antigravity
from aigauge.providers.antigravity import (
    AntigravityProvider,
    normalize_cli_path,
    resolve_cli,
)
from aigauge.settings_dialog import SettingsDialog


def _sync(provider, monkeypatch):
    monkeypatch.setattr(
        provider, "_run_async", lambda work, on_done: on_done(work())
    )


def _dialog(qtbot, monkeypatch, config=None, autodetected=None):
    monkeypatch.setattr(
        "aigauge.settings_dialog.resolve_cli", lambda _: autodetected
    )
    monkeypatch.setattr("aigauge.settings_dialog.set_start_at_login", lambda _: None)
    monkeypatch.setattr(Config, "save", lambda self: None)
    dialog = SettingsDialog(config or Config())
    qtbot.addWidget(dialog)
    return dialog


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("  C:/tools/agy.exe  ", "C:/tools/agy.exe"),
        ('"C:/tools/agy.exe"', "C:/tools/agy.exe"),
        ("'C:/tools/agy.exe'", "C:/tools/agy.exe"),
        ("   ", None),
        ("", None),
    ],
)
def test_normalize_cli_path_trims_and_unquotes(value, expected):
    assert normalize_cli_path(value) == expected


def test_normalize_cli_path_expands_home_and_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("AGY_BIN", str(tmp_path / "agy.exe"))
    assert Path(normalize_cli_path("~/bin/agy.exe")) == tmp_path / "bin" / "agy.exe"
    assert normalize_cli_path("%AGY_BIN%") == str(tmp_path / "agy.exe")


def test_provider_uses_explicit_existing_file_without_autodetect(monkeypatch, tmp_path):
    executable = tmp_path / "agy.exe"
    executable.touch()
    provider = AntigravityProvider(cli_path=f' "{executable}" ')
    _sync(provider, monkeypatch)
    which = lambda _: pytest.fail("explicit path must not trigger PATH lookup")
    monkeypatch.setattr(antigravity.shutil, "which", which)
    calls = []
    monkeypatch.setattr(
        antigravity,
        "_invoke_cli",
        lambda path: calls.append(path)
        or subprocess.CompletedProcess([], 0, json.dumps({
            "status": "SUCCESS", "num_turns": 0, "usage": {"total_tokens": 0},
            "command": {"name": "usage", "data": {"groups": []}},
        }), ""),
    )
    result = []
    provider.refresh(result.append)
    assert calls == [str(executable)]
    assert result[0].status is SnapshotStatus.OK


def test_provider_reports_missing_explicit_file_without_autodetect(
    monkeypatch, tmp_path
):
    missing = tmp_path / "missing agy.exe"
    provider = AntigravityProvider(cli_path=f' "{missing}" ')
    _sync(provider, monkeypatch)
    monkeypatch.setattr(
        antigravity.shutil, "which",
        lambda _: pytest.fail("invalid explicit path must not autodetect"),
    )
    result = []
    provider.refresh(result.append)
    assert result[0].status is SnapshotStatus.ERROR
    assert result[0].error == f"agy CLI not found at {missing}"


def test_none_keeps_path_then_windows_fallback_order(monkeypatch, tmp_path):
    path_cli = tmp_path / "path-agy.exe"
    fallback = tmp_path / "agy" / "bin" / "agy.exe"
    fallback.parent.mkdir(parents=True)
    fallback.touch()
    monkeypatch.setattr(antigravity.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(antigravity.shutil, "which", lambda _: str(path_cli))
    assert resolve_cli(None) == str(path_cli)
    monkeypatch.setattr(antigravity.shutil, "which", lambda _: None)
    assert resolve_cli(None) == str(fallback)


def test_settings_path_field_loads_saves_normalized_path_and_empty_as_none(
    qtbot, monkeypatch, tmp_path
):
    path = tmp_path / "agy.exe"
    config = Config()
    config.antigravity.cli_path = f'  "{path}"  '
    dialog = _dialog(qtbot, monkeypatch, config)
    assert dialog.antigravity_cli_path_edit.text() == f'  "{path}"  '
    dialog.apply_to(config)
    assert config.antigravity.cli_path == str(path)
    dialog.antigravity_cli_path_edit.clear()
    dialog.apply_to(config)
    assert config.antigravity.cli_path is None


def test_settings_browse_populates_path(qtbot, monkeypatch, tmp_path):
    dialog = _dialog(qtbot, monkeypatch)
    selected = tmp_path / "agy.exe"
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", lambda *args: (str(selected), "")
    )
    dialog.antigravity_cli_browse_button.click()
    assert dialog.antigravity_cli_path_edit.text() == str(selected)


@pytest.mark.parametrize(
    ("configured", "detected", "exists", "expected"),
    [
        ("custom", None, True, "Using: {path}"),
        ("custom", None, False, "Not found: {path}"),
        ("", "auto", True, "Using auto-detected: {path}"),
        (
            "", None, False,
            "agy CLI not found. Install the Antigravity CLI or set its path.",
        ),
    ],
)
def test_settings_path_status_text(qtbot, monkeypatch, tmp_path, configured,
                                  detected, exists, expected):
    custom = tmp_path / "configured agy.exe"
    auto = tmp_path / "auto agy.exe"
    if exists:
        (custom if configured else auto).touch()
    config = Config()
    config.antigravity.cli_path = str(custom) if configured else None
    dialog = _dialog(
        qtbot, monkeypatch, config, autodetected=str(auto) if detected else None
    )
    if not configured:
        dialog.antigravity_cli_path_edit.clear()
    path = custom if configured else auto
    expected_text = expected.format(path=path)
    assert dialog.antigravity_cli_path_status.text() == expected_text
