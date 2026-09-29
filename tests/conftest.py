import os
import sys
from pathlib import Path

import pytest

# Make `src/` importable
SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from aigauge import windows_toast


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
    """Redirect %APPDATA% so config writes never touch the user's real folder."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    yield
