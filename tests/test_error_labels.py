
from aigauge.app import _preserve_error_metrics
from aigauge.config import Config
from aigauge.models import SnapshotStatus, UsageMetric, UsageSnapshot
from aigauge.widget import UsageWidget

def test_config_errors_do_not_preserve_metrics_but_other_errors_do():
    previous = UsageSnapshot(
        provider="antigravity",
        status=SnapshotStatus.OK,
        metrics=[UsageMetric("Gemini 5h", 42.0)],
    )
    config_error = UsageSnapshot(
        provider="antigravity",
        status=SnapshotStatus.ERROR,
        error="Not the agy CLI",
        raw={"config_error": True},
    )
    ordinary_error = UsageSnapshot(
        provider="antigravity", status=SnapshotStatus.ERROR, error="agy timed out"
    )

    assert _preserve_error_metrics(config_error, previous).metrics == []
    assert _preserve_error_metrics(ordinary_error, previous).metrics == previous.metrics

def test_error_labels_show_reason_and_keep_api_after_network(qtbot):
    cases = [
        ("Claude", "request timed out", True, "timeout · stale"),
        ("Claude", "ConnectionError: unavailable", True, "offline · stale"),
        ("Claude", "unclassified failure", True, "error · stale"),
        ("Antigravity", "agy CLI not found at C:/x/agy.exe", False,
         "error · agy not found"),
        ("Antigravity", "Not the agy CLI: C:/x/notepad.exe", False,
         "error · not agy"),
        (
            "Antigravity",
            "Post https://googleapis.com/: connectex: dial tcp failed",
            False,
            "error · offline",
        ),
    ]
    for provider, error, stale, expected in cases:
        widget = UsageWidget(Config())
        qtbot.addWidget(widget)
        widget.update_snapshot(
            UsageSnapshot(
                provider=provider.lower(),
                status=SnapshotStatus.ERROR,
                error=error,
                metrics=[UsageMetric("Session", 40.0)] if stale else [],
            ),
            provider,
        )
        assert expected in widget._tiles[provider.lower()].status.text()
