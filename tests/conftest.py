import os
import sys
from pathlib import Path

import pytest

# Make `src/` importable
SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from aigauge import windows_toast
from aigauge.providers import _resets_common, antigravity


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "real_windows_toast: exercise toast internals with mocked winreg and winrt",
    )


@pytest.fixture(autouse=True)
def block_native_toast(request, monkeypatch):
    """Keep native toast and registry registration disabled by default."""
    if request.node.get_closest_marker("real_windows_toast"):
        return
    monkeypatch.setattr(windows_toast, "show_toast", lambda *args, **kwargs: False)
    monkeypatch.setattr(windows_toast, "ensure_registered", lambda: False)


@pytest.fixture(autouse=True)
def isolated_appdata(tmp_path, monkeypatch):
    """Keep config and log discovery inside the test directory on every OS."""
    for name in ("APPDATA", "LOCALAPPDATA", "HOME", "USERPROFILE", "XDG_CONFIG_HOME"):
        monkeypatch.setenv(name, str(tmp_path))
    yield


@pytest.fixture(autouse=True)
def reset_process_provider_state():
    """Keep module-level provider state isolated between tests."""
    _resets_common._PROCESS_STATES.clear()
    antigravity._PROCESS_LATCHED_ERROR = None
    yield
    _resets_common._PROCESS_STATES.clear()
    antigravity._PROCESS_LATCHED_ERROR = None
