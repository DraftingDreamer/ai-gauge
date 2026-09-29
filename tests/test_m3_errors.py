import json
import subprocess

from aigauge.app import _preserve_error_metrics
from aigauge.config import Config
from aigauge.models import SnapshotStatus, UsageMetric, UsageSnapshot
from aigauge.providers import antigravity
from aigauge.providers.antigravity import AntigravityProvider
from aigauge.settings_dialog import SettingsDialog
from aigauge.widget import UsageWidget


def _sync(provider, monkeypatch):
    monkeypatch.setattr(provider, "_run_async", lambda work, done: done(work()))


def _provider_for_payload(monkeypatch, tmp_path, payload):
    cli = tmp_path / "agy.exe"
    cli.touch()
    provider = AntigravityProvider(cli_path=str(cli))
    _sync(provider, monkeypatch)
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, json.dumps(payload), "")

    monkeypatch.setattr(antigravity.subprocess, "run", run)
    return provider, calls


def test_offline_eligibility_error_does_not_latch(monkeypatch, tmp_path):
    payload = {
        "conversation_id": "test",
        "duration_seconds": 0.1,
        "error": (
            'Eligibility check failed: Post "https://googleapis.com/": '
            "proxyconnect tcp: dial tcp 127.0.0.1:9: connectex: No connection"
        ),
        "num_turns": 0,
        "response": "",
        "status": "ERROR",
        "usage": {"total_tokens": 0},
    }
    provider, calls = _provider_for_payload(monkeypatch, tmp_path, payload)
    snapshots = []

    provider.refresh(snapshots.append)
    provider.refresh(snapshots.append)

    assert len(calls) == 2
    assert snapshots[0].status is SnapshotStatus.ERROR
    assert snapshots[0].error.startswith("agy error:")
    assert provider._latched_error is None


def test_token_usage_latches_and_stops_future_calls(monkeypatch, tmp_path):
    for usage_change in ({"num_turns": 1}, {"total_tokens": 1}):
        payload = {
            "status": "SUCCESS",
            "num_turns": 0,
            "usage": {"total_tokens": 0},
            "command": {"name": "usage", "data": {"groups": []}},
        }
        payload.update({k: v for k, v in usage_change.items() if k == "num_turns"})
        if "total_tokens" in usage_change:
            payload["usage"]["total_tokens"] = usage_change["total_tokens"]
        provider, calls = _provider_for_payload(monkeypatch, tmp_path, payload)
        snapshots = []

        provider.refresh(snapshots.append)
        provider.refresh(snapshots.append)

        assert len(calls) == 1
        assert snapshots[0].error == snapshots[1].error
        assert provider._latched_error


def test_indeterminate_usage_latches(monkeypatch, tmp_path):
    provider, calls = _provider_for_payload(
        monkeypatch, tmp_path, {"status": "ERROR", "error": "unknown"}
    )
    snapshots = []

    provider.refresh(snapshots.append)
    provider.refresh(snapshots.append)

    assert len(calls) == 1
    assert provider._latched_error


def test_success_without_command_and_zero_tokens_does_not_latch(monkeypatch, tmp_path):
    payload = {
        "status": "SUCCESS",
        "num_turns": 0,
        "usage": {"total_tokens": 0},
    }
    provider, calls = _provider_for_payload(monkeypatch, tmp_path, payload)
    snapshots = []

    provider.refresh(snapshots.append)
    provider.refresh(snapshots.append)

    assert len(calls) == 2
    assert all(s.status is SnapshotStatus.ERROR for s in snapshots)
    assert snapshots[0].error == "unexpected agy output: command is missing"
    assert provider._latched_error is None


def test_wrong_explicit_executable_is_rejected_without_running(monkeypatch, tmp_path):
    executable = tmp_path / "notepad.exe"
    executable.touch()
    provider = AntigravityProvider(cli_path=str(executable))
    _sync(provider, monkeypatch)
    monkeypatch.setattr(
        antigravity.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not run")),
    )
    snapshots = []

    provider.refresh(snapshots.append)

    assert snapshots[0].error.startswith("Not the agy CLI:")
    assert snapshots[0].raw["config_error"] is True


def test_missing_explicit_path_is_configuration_error(monkeypatch, tmp_path):
    missing = tmp_path / "agy.exe"
    provider = AntigravityProvider(cli_path=str(missing))
    _sync(provider, monkeypatch)
    snapshots = []

    provider.refresh(snapshots.append)

    assert snapshots[0].error.startswith("agy CLI not found at")
    assert snapshots[0].raw["config_error"] is True


def test_existing_agy_executable_is_invoked(monkeypatch, tmp_path):
    payload = {
        "status": "SUCCESS",
        "num_turns": 0,
        "usage": {"total_tokens": 0},
        "command": {"name": "usage", "data": {"groups": []}},
    }
    provider, calls = _provider_for_payload(monkeypatch, tmp_path, payload)
    snapshots = []

    provider.refresh(snapshots.append)

    assert len(calls) == 1
    assert snapshots[0].status is SnapshotStatus.OK


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
