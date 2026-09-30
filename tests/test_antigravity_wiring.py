import pytest
from types import SimpleNamespace

from aigauge import app as app_module
from aigauge import config as config_module
from aigauge.app import App, _enabled_providers
from aigauge.config import ColorThresholds, Config
from aigauge.gauge import thresholds_for_provider
from aigauge.mcp_server import _configured_account_ids
from aigauge.menubar import PROVIDER_LABELS
from aigauge.settings_dialog import SettingsDialog
from aigauge.widget import PROVIDER_ORDER


def test_antigravity_config_defaults_and_legacy_json(tmp_path, monkeypatch):
    config = Config()
    assert config.providers.antigravity is False
    assert config.antigravity.colors == ColorThresholds()
    assert config.antigravity.cli_path is None
    assert config.antigravity.show_gemini is True
    assert config.antigravity.show_third_party is True
    config_file = tmp_path / "config.json"
    config_file.write_text('{"providers": {"claude": false}}', encoding="utf-8")
    monkeypatch.setattr(config_module, "config_path", lambda: config_file)
    legacy = Config.load()
    assert legacy.providers.antigravity is False
    assert legacy.antigravity.cli_path is None


def test_antigravity_threshold_label_and_order():
    config = Config()
    colors = ColorThresholds(green_color="#123456")
    config.antigravity.colors = colors
    assert thresholds_for_provider(config, "antigravity") == colors
    assert PROVIDER_LABELS["antigravity"] == "Ag"
    assert PROVIDER_ORDER.index("antigravity") == PROVIDER_ORDER.index("openrouter") + 1


def test_mcp_account_ids_follow_antigravity_toggle():
    config = Config()
    config.providers.antigravity = True
    assert "antigravity" in _configured_account_ids(config)
    config.providers.antigravity = False
    assert "antigravity" not in _configured_account_ids(config)


def test_app_builds_antigravity_provider_with_config_and_tile(monkeypatch):
    config = Config()
    config.providers.claude = False
    config.providers.codex = False
    config.providers.copilot = False
    config.providers.antigravity = True
    config.antigravity.cli_path = "C:/tools/agy.exe"
    config.antigravity.show_gemini = False
    config.antigravity.show_third_party = True
    created = []
    ensured = []

    def fake_provider(**kwargs):
        created.append(kwargs)
        return object()

    monkeypatch.setattr(app_module, "AntigravityProvider", fake_provider)
    app = App.__new__(App)
    app._config = config
    app._providers = {}
    app._snapshots = {}
    app._widget = SimpleNamespace(
        _tiles={},
        ensure_tile=lambda account_id, label: ensured.append((account_id, label)),
        remove_tile=lambda account_id: None,
    )

    assert "antigravity" in _enabled_providers(config)
    app._build_providers()

    assert created == [{
        "cli_path": "C:/tools/agy.exe",
        "show_gemini": False,
        "show_third_party": True,
    }]
    assert "antigravity" in app._providers
    assert ensured == [("antigravity", "Antigravity")]


def test_settings_dialog_shows_and_saves_antigravity_options(qtbot, monkeypatch):
    monkeypatch.setattr("aigauge.settings_dialog.resolve_cli", lambda _: "agy-test")
    monkeypatch.setattr("aigauge.settings_dialog.set_start_at_login", lambda _: None)
    config = Config()
    monkeypatch.setattr(Config, "save", lambda self: None)
    dialog = SettingsDialog(config)
    qtbot.addWidget(dialog)

    index = next(
        i for i in range(dialog.tabs.count()) if dialog.tabs.tabText(i) == "Antigravity"
    )
    assert dialog.antigravity_cli_path_edit.text() == ""
    assert dialog.antigravity_cli_path_status.text() == (
        "Using auto-detected: agy-test"
    )
    dialog.antigravity_show_gemini_cb.setChecked(False)
    dialog.apply_to(config)

    assert config.antigravity.show_gemini is False
    dialog.show_provider("antigravity")
    assert dialog.tabs.currentIndex() == index


from PyQt6.QtWidgets import QFileDialog
from aigauge.config import Config

def _dialog(qtbot, monkeypatch, config=None, autodetected=None):
    monkeypatch.setattr(
        "aigauge.settings_dialog.resolve_cli", lambda _: autodetected
    )
    monkeypatch.setattr("aigauge.settings_dialog.set_start_at_login", lambda _: None)
    monkeypatch.setattr(Config, "save", lambda self: None)
    dialog = SettingsDialog(config or Config())
    qtbot.addWidget(dialog)
    return dialog

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
    custom_name = "agy.exe" if expected == "Using: {path}" else "configured agy.exe"
    custom = tmp_path / custom_name
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

def test_settings_identifies_wrong_cli_name(qtbot, monkeypatch, tmp_path):
    executable = tmp_path / "notepad.exe"
    executable.touch()
    monkeypatch.setattr("aigauge.settings_dialog.resolve_cli", lambda _: None)
    monkeypatch.setattr("aigauge.settings_dialog.set_start_at_login", lambda _: None)
    config = Config()
    config.antigravity.cli_path = str(executable)
    dialog = SettingsDialog(config)
    qtbot.addWidget(dialog)

    assert dialog.antigravity_cli_path_status.text() == (
        f"Not the agy CLI: {executable}"
    )
