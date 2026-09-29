import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, Mock
from xml.etree import ElementTree

import pytest
from PyQt6.QtWidgets import QSystemTrayIcon

from aigauge import app as app_module
from aigauge import windows_toast
from aigauge.app import App
from aigauge.config import Config
from aigauge.providers._resets_common import ResetEvent


def fake_registry(monkeypatch, initial=None):
    values = dict(initial or {})
    key = MagicMock()
    key.__enter__.return_value = key
    create = Mock(return_value=key)
    set_value = Mock(side_effect=lambda _, name, __, kind, value: values.__setitem__(name, (value, kind)))

    def query(_, name):
        if name not in values:
            raise FileNotFoundError(name)
        return values[name]

    registry = SimpleNamespace(
        HKEY_CURRENT_USER=object(), REG_SZ=1, CreateKey=create,
        QueryValueEx=Mock(side_effect=query), SetValueEx=set_value,
    )
    monkeypatch.setitem(sys.modules, "winreg", registry)
    return registry, values


def fake_winrt(monkeypatch):
    for name in (
        "winrt", "winrt.windows", "winrt.windows.data",
        "winrt.windows.data.xml", "winrt.windows.ui",
    ):
        module = ModuleType(name)
        module.__path__ = []
        monkeypatch.setitem(sys.modules, name, module)
    document = Mock()
    xml_module = ModuleType("winrt.windows.data.xml.dom")
    xml_module.XmlDocument = Mock(return_value=document)
    monkeypatch.setitem(sys.modules, xml_module.__name__, xml_module)
    notifier = Mock()
    notifications = ModuleType("winrt.windows.ui.notifications")
    notifications.ToastNotification = Mock(return_value="toast")
    notifications.ToastNotificationManager = SimpleNamespace(
        create_toast_notifier_with_id=Mock(return_value=notifier)
    )
    monkeypatch.setitem(sys.modules, notifications.__name__, notifications)
    return document, notifier, notifications


@pytest.fixture(autouse=True)
def no_real_toast(monkeypatch, request):
    monkeypatch.setattr(windows_toast, "_registered", False)
    monkeypatch.setattr(windows_toast, "sys", SimpleNamespace(platform="win32"))
    if request.node.get_closest_marker("real_windows_toast"):
        fake_registry(monkeypatch)
        fake_winrt(monkeypatch)


def test_xml_escapes_text_and_protocol_url():
    title = 'Title & <tag> "quoted"'
    message = "Message > < & 'single'"
    url = 'https://example.test/?a=1&b=<tag>&q="double"&s=\'single\''
    xml = windows_toast.build_toast_xml(title, message, url)
    root = ElementTree.fromstring(xml)
    assert root.attrib == {"activationType": "protocol", "launch": url}
    assert [node.text for node in root.findall("./visual/binding/text")] == [title, message]
    assert "Title &amp; &lt;tag&gt;" in xml
    assert "Message &gt; &lt; &amp;" in xml
    assert "&quot;double&quot;" in xml
    assert "&amp;" in xml


def test_xml_without_url_has_no_protocol():
    root = ElementTree.fromstring(windows_toast.build_toast_xml("T", "M", None))
    assert root.tag == "toast"
    assert root.attrib == {}


@pytest.mark.real_windows_toast
def test_ensure_registered_writes_only_changed_values(monkeypatch):
    registry, values = fake_registry(monkeypatch)
    icon = str(windows_toast.Path(windows_toast.__file__).resolve().parent / "assets" / "aigaugeicon.png")
    assert windows_toast.ensure_registered()
    registry.CreateKey.assert_called_once_with(
        registry.HKEY_CURRENT_USER,
        r"Software\Classes\AppUserModelId\AloeDesk.AIGauge",
    )
    assert values == {
        "DisplayName": ("AI Gauge", registry.REG_SZ),
        "IconUri": (icon, registry.REG_SZ),
    }
    assert registry.SetValueEx.call_count == 2
    registry.SetValueEx.reset_mock()
    assert windows_toast.ensure_registered()
    registry.SetValueEx.assert_not_called()


@pytest.mark.real_windows_toast
def test_ensure_registered_omits_missing_icon(monkeypatch):
    registry, values = fake_registry(monkeypatch)
    monkeypatch.setattr(windows_toast.Path, "is_file", lambda _: False)
    assert windows_toast.ensure_registered()
    assert values == {"DisplayName": ("AI Gauge", registry.REG_SZ)}


@pytest.mark.real_windows_toast
def test_ensure_registered_failure_warns(monkeypatch, caplog):
    registry, _ = fake_registry(monkeypatch)
    registry.CreateKey.side_effect = OSError("registry denied")
    with caplog.at_level("WARNING", logger="aigauge.windows_toast"):
        assert not windows_toast.ensure_registered()
    assert "registry denied" in caplog.text


@pytest.mark.real_windows_toast
def test_show_toast_success_reuses_registration(monkeypatch):
    registered = Mock(return_value=True)
    monkeypatch.setattr(windows_toast, "ensure_registered", registered)
    document, notifier, notifications = fake_winrt(monkeypatch)
    assert windows_toast.show_toast("Title", "Body", "https://example.test/one")
    assert windows_toast.show_toast("Title", "Body", "https://example.test/two")
    registered.assert_called_once_with()
    notifications.ToastNotificationManager.create_toast_notifier_with_id.assert_called_with(
        windows_toast.AUMID
    )
    assert document.load_xml.call_count == 2
    assert notifier.show.call_count == 2
    assert notifier.show.call_args.args == ("toast",)


@pytest.mark.real_windows_toast
def test_show_toast_import_failure_warns(monkeypatch, caplog):
    monkeypatch.setattr(windows_toast, "ensure_registered", Mock(return_value=True))
    monkeypatch.setitem(sys.modules, "winrt.windows.data.xml.dom", None)
    with caplog.at_level("WARNING", logger="aigauge.windows_toast"):
        assert not windows_toast.show_toast("Title", "Body", None)
    assert "Windows toast notification failed" in caplog.text


@pytest.mark.real_windows_toast
def test_show_toast_registration_failure_does_not_import_winrt(monkeypatch):
    monkeypatch.setattr(windows_toast, "ensure_registered", Mock(return_value=False))
    monkeypatch.setitem(sys.modules, "winrt.windows.data.xml.dom", None)
    assert not windows_toast.show_toast("Title", "Body", None)


@pytest.mark.real_windows_toast
def test_show_toast_failure_warns(monkeypatch, caplog):
    monkeypatch.setattr(windows_toast, "ensure_registered", Mock(return_value=True))
    _, notifier, _ = fake_winrt(monkeypatch)
    notifier.show.side_effect = OSError("show failed")
    with caplog.at_level("WARNING", logger="aigauge.windows_toast"):
        assert not windows_toast.show_toast("Title", "Body", None)
    assert "show failed" in caplog.text


@pytest.mark.real_windows_toast
def test_show_toast_non_windows_has_no_side_effect(monkeypatch):
    monkeypatch.setattr(windows_toast, "sys", SimpleNamespace(platform="linux"))
    registered = Mock()
    monkeypatch.setattr(windows_toast, "ensure_registered", registered)
    assert not windows_toast.show_toast("Title", "Body", None)
    registered.assert_not_called()


def make_app(monkeypatch, tray, platform):
    monkeypatch.setattr(app_module, "sys", SimpleNamespace(platform=platform))
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: True))
    config = Config()
    config.codex_resets.last_event_key = "landed:old"
    monkeypatch.setattr(Config, "save", Mock())
    reset = ResetEvent(
        "landed", "new", app_module.datetime.now(app_module.timezone.utc),
        "regular reset", "Private post content", "https://example.test/new",
    )
    app = App.__new__(App)
    app._config = config
    app._providers = {"codex_resets": SimpleNamespace(latest_event=reset)}
    app._tray = tray
    return app


def test_app_windows_toast_succeeds_without_tray(monkeypatch, caplog):
    show = Mock(return_value=True)
    monkeypatch.setattr(windows_toast, "show_toast", show)
    tray = Mock()
    app = make_app(monkeypatch, tray, "win32")
    with caplog.at_level("INFO", logger="aigauge.app"):
        app._on_reset_event("codex_resets")
    show.assert_called_once_with(
        "Codex reset landed", "Usage limits were refilled. Click to open the post.",
        "https://example.test/new",
    )
    tray.showMessage.assert_not_called()
    assert "event_id=new via=toast" in caplog.text
    app._tray = None
    app._providers["codex_resets"].latest_event = ResetEvent(
        "landed", "newer", app_module.datetime.now(app_module.timezone.utc),
        "regular reset", "Private post content", "https://example.test/newer",
    )
    monkeypatch.setattr(app_module.time, "monotonic", lambda: 100.0)
    app._last_reset_notification_shown_at = 0.0
    app._on_reset_event("codex_resets")
    assert show.call_count == 2


def test_default_toast_guard_never_writes_registry(monkeypatch):
    registry, _ = fake_registry(monkeypatch)
    registry.CreateKey.side_effect = AssertionError("real registry write attempted")
    registry.SetValueEx.side_effect = AssertionError("real registry write attempted")
    tray = Mock()
    app = make_app(monkeypatch, tray, "win32")
    app._on_reset_event("codex_resets")
    registry.CreateKey.assert_not_called()
    registry.SetValueEx.assert_not_called()
    tray.showMessage.assert_called_once()


def test_app_windows_toast_failure_uses_tray(monkeypatch, caplog):
    monkeypatch.setattr(windows_toast, "show_toast", Mock(return_value=False))
    tray = Mock()
    app = make_app(monkeypatch, tray, "win32")
    with caplog.at_level("INFO", logger="aigauge.app"):
        app._on_reset_event("codex_resets")
    tray.showMessage.assert_called_once()
    assert app._last_reset_notification_url == "https://example.test/new"
    assert "event_id=new via=tray" in caplog.text


def test_app_windows_toast_failure_without_tray_skips(monkeypatch, caplog):
    monkeypatch.setattr(windows_toast, "show_toast", Mock(return_value=False))
    app = make_app(monkeypatch, None, "win32")
    with caplog.at_level("INFO", logger="aigauge.app"):
        app._on_reset_event("codex_resets")
    assert "reason=no tray" in caplog.text


def test_app_non_windows_uses_tray(monkeypatch, caplog):
    show = Mock()
    monkeypatch.setattr(windows_toast, "show_toast", show)
    tray = Mock()
    app = make_app(monkeypatch, tray, "linux")
    with caplog.at_level("INFO", logger="aigauge.app"):
        app._on_reset_event("codex_resets")
    show.assert_not_called()
    tray.showMessage.assert_called_once()
    assert "event_id=new via=tray" in caplog.text
