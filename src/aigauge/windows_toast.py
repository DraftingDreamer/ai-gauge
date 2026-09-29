"""Native Windows toast notifications for reset announcements."""

import logging
import sys
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr


AUMID = "AloeDesk.AIGauge"
DISPLAY_NAME = "AI Gauge"

log = logging.getLogger(__name__)
_registered = False


def ensure_registered() -> bool:
    """Register the app identity used by Windows Notification Center."""
    try:
        import winreg

        key_path = rf"Software\Classes\AppUserModelId\{AUMID}"
        values = {"DisplayName": DISPLAY_NAME}
        icon_path = Path(__file__).resolve().parent / "assets" / "aigaugeicon.png"
        if icon_path.is_file():
            values["IconUri"] = str(icon_path)

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            for name, value in values.items():
                try:
                    current, value_type = winreg.QueryValueEx(key, name)
                except FileNotFoundError:
                    current, value_type = None, None
                if current != value or value_type != winreg.REG_SZ:
                    winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("Windows toast registration failed: %s", str(exc).replace("\n", " "))
        return False


def build_toast_xml(title: str, message: str, url: str | None) -> str:
    """Build a toast whose protocol activation opens its own event URL."""
    opening = (
        f"<toast activationType=\"protocol\" launch={quoteattr(url)}>"
        if url else "<toast>"
    )
    return (
        f"{opening}<visual><binding template=\"ToastGeneric\">"
        f"<text>{escape(title)}</text><text>{escape(message)}</text>"
        "</binding></visual></toast>"
    )


def show_toast(title: str, message: str, url: str | None) -> bool:
    """Show one toast, returning False so callers can use a tray fallback."""
    global _registered
    if sys.platform != "win32":
        return False
    try:
        if not _registered:
            if not ensure_registered():
                return False
            _registered = True

        from winrt.windows.data.xml.dom import XmlDocument
        from winrt.windows.ui.notifications import (
            ToastNotification,
            ToastNotificationManager,
        )

        document = XmlDocument()
        document.load_xml(build_toast_xml(title, message, url))
        notifier = ToastNotificationManager.create_toast_notifier_with_id(AUMID)
        notifier.show(ToastNotification(document))
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("Windows toast notification failed: %s", str(exc).replace("\n", " "))
        return False
