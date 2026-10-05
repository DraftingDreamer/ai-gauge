"""Exercise the real Codex page scripts against a small DOM model."""

from __future__ import annotations

from datetime import datetime
from functools import partial
import json
import shutil
import subprocess

import pytest

from aigauge.models import SnapshotStatus
from aigauge.providers import codex
from aigauge.providers._codex_page import EXTRACTOR_JS, VERIFY_JS

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not available")

HARNESS = r"""
const fs = require('fs');
const spec = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const document = { title: spec.title || 'Codex', __aigaugeCodexOverviewClicked: false };
const elements = (spec.elements || []).map(item => {
  const attrs = {...(item.attrs || {})};
  const el = {
    tagName: item.tag || 'div',
    innerText: item.text || '', textContent: item.text || '',
    hidden: !!item.hidden, parentElement: null, className: item.className || '',
    getAttribute: name => attrs[name] == null ? null : String(attrs[name]),
    setAttribute: (name, value) => { attrs[name] = String(value); },
    click: () => {
      spec.clicks = (spec.clicks || 0) + 1;
      if (item.onClick) item.onClick();
    },
  };
  el.__attrs = attrs;
  return el;
});
document.body = {
  innerText: spec.body || '', textContent: spec.body || '', hidden: false,
  parentElement: document, getAttribute: () => null,
};
document.documentElement = { dataset: {} };
for (const el of elements) el.parentElement = document.body;
document.querySelectorAll = selector => {
  if (selector.includes('a[href]')) return elements.filter(el => el.tagName === 'a');
  if (selector.includes('button') || selector.includes('[role="tab"]') || selector.includes('[role="button"]')) {
    return elements.filter(el => ['button', 'a'].includes(el.tagName) || el.__attrs.role === 'tab' || el.__attrs.role === 'button');
  }
  return elements.filter(el => ['article', 'section', 'div', 'li'].includes(el.tagName) || el.__attrs.role === 'group');
};
document.querySelector = () => null;
global.document = document;
global.getComputedStyle = el => ({
  display: String((el.__attrs || {}).style || '').includes('display:none') ? 'none' : 'block',
  visibility: String((el.__attrs || {}).style || '').includes('visibility:hidden') ? 'hidden' : 'visible',
});
global.location = {
  hostname: spec.hostname || 'chatgpt.com',
  pathname: spec.pathname || '/settings/usage',
  href: spec.href || `https://chatgpt.com${spec.pathname || '/settings/usage'}?tab=overview`,
};
const source = fs.readFileSync(process.argv[3], 'utf8');
const results = [];
for (let attempt = 0; attempt < (spec.repeat || 1); attempt++) results.push(eval(source));
process.stdout.write(JSON.stringify({result: results[results.length - 1], results, clicks: spec.clicks || 0}));
"""


def run_js(tmp_path, script: str, spec: dict) -> dict:
    harness_path = tmp_path / "harness.js"
    script_path = tmp_path / "page-script.js"
    spec_path = tmp_path / "page.json"
    harness_path.write_text(HARNESS, encoding="utf-8")
    script_path.write_text(script, encoding="utf-8")
    spec_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    completed = subprocess.run(
        ["node", str(harness_path), str(spec_path), str(script_path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(completed.stdout)


def tab(name: str, selected: bool, *, hidden: bool = False) -> dict:
    return {
        "tag": "button",
        "text": name,
        "attrs": {"aria-pressed": str(selected).lower()},
        "hidden": hidden,
    }


def test_analytics_route_selects_overview_once_then_waits_for_async_card(tmp_path):
    analytics = run_js(
        tmp_path,
        EXTRACTOR_JS,
        {
            "pathname": "/codex/cloud/settings/analytics",
            "body": "Usage Overview Analytics Usage history Tasks 80.4% Subagents 19.2% Plan usage history Weekly limits Period % of limit used Sep 21-26 73.9%",
            "elements": [tab("概覽", False), tab("分析", True)],
        },
    )
    assert analytics["result"]["__retry_after_ms"] == 1200
    assert analytics["result"]["weekly"] is None
    assert analytics["clicks"] == 1

    hydrated = run_js(
        tmp_path,
        EXTRACTOR_JS,
        {
            "body": "用量 每週上限 5 天 10 小時後重設 剩餘 94%",
            "elements": [
                tab("概覽", True),
                tab("分析", False),
                {"tag": "div", "text": "每週上限 5 天 10 小時後重設 剩餘 94%"},
            ],
        },
    )
    assert hydrated["result"]["overview_ready"] is True
    assert hydrated["result"]["weekly"]["percent"] == 94
    assert hydrated["result"]["weekly"]["kind"] == "remaining"
    assert hydrated["result"]["weekly"]["reset_text"] == "5 天 10 小時"
    assert hydrated["clicks"] == 0


def test_selected_overview_is_not_clicked_and_english_card_is_read(tmp_path):
    outcome = run_js(
        tmp_path,
        EXTRACTOR_JS,
        {
            "body": "Usage Overview Weekly limits 5 days 10 hours until reset 0% remaining",
            "elements": [
                tab("Overview", True),
                tab("Analytics", False),
                {"tag": "div", "text": "Weekly limits 5 days 10 hours until reset 0% remaining"},
            ],
        },
    )
    assert outcome["result"]["weekly"]["percent"] == 0
    assert outcome["result"]["weekly"]["reset_text"] == "5 days 10 hours"
    assert outcome["clicks"] == 0


@pytest.mark.parametrize("percent", [0, 100])
def test_overview_accepts_valid_percent_boundaries(tmp_path, percent):
    outcome = run_js(
        tmp_path,
        EXTRACTOR_JS,
        {
            "body": f"Weekly limits 2 days until reset {percent}% used",
            "elements": [tab("Overview", True), {"tag": "div", "text": f"Weekly limits 2 days until reset {percent}% used"}],
        },
    )
    assert outcome["result"]["weekly"]["percent"] == percent


@pytest.mark.parametrize("percent_text", ["101% used", "-1% used", "12%", "NaN% used"])
def test_overview_rejects_out_of_range_or_directionless_percent(tmp_path, percent_text):
    outcome = run_js(
        tmp_path,
        EXTRACTOR_JS,
        {
            "body": f"Weekly limits 2 days until reset {percent_text}",
            "elements": [tab("Overview", True), {"tag": "div", "text": f"Weekly limits 2 days until reset {percent_text}"}],
        },
    )
    assert outcome["result"].get("__retry_after_ms") == 1200
    assert outcome["result"]["weekly"] is None


@pytest.mark.parametrize(
    "history",
    [
        "Usage history Tasks 80.4% Subagents 19.2% Plan usage history Weekly limits Period % of limit used Sep 21-26 73.9%",
        "Weekly limits Sep 21-26 73.9% of limit used",
    ],
)
def test_history_percentages_and_similar_weekly_headers_do_not_pass(tmp_path, history):
    outcome = run_js(
        tmp_path,
        EXTRACTOR_JS,
        {"body": history, "elements": [tab("Overview", True)]},
    )
    assert outcome["result"].get("__retry_after_ms") == 1200
    assert outcome["result"]["weekly"] is None


def test_hidden_tabs_and_cards_are_ignored(tmp_path):
    outcome = run_js(
        tmp_path,
        EXTRACTOR_JS,
        {
            "body": "Usage history Weekly limits Period % of limit used Sep 21-26 73.9%",
            "elements": [
                tab("Overview", False, hidden=True),
                tab("Analytics", True, hidden=True),
                {"tag": "div", "text": "Weekly limits 3 days until reset 94% remaining", "hidden": True},
            ],
        },
    )
    assert outcome["result"]["weekly"] is None
    assert outcome["clicks"] == 0


@pytest.mark.parametrize(
    ("path", "title", "body", "expected"),
    [
        ("/login", "Sign in", "Sign in to continue", "logged_out"),
        ("/settings/usage", "Just a moment...", "Verify you are human Cloudflare", "security_verification"),
    ],
)
def test_login_and_security_pages_are_not_redirected_or_verified(tmp_path, path, title, body, expected):
    spec = {"pathname": path, "title": title, "body": body, "elements": [tab("概覽", False)]}
    extracted = run_js(tmp_path, EXTRACTOR_JS, spec)
    verified = run_js(tmp_path, VERIFY_JS, spec)
    assert extracted["result"].get(expected) is True or extracted["result"].get("logged_out") is True
    assert verified["result"] is False
    assert extracted["clicks"] == 0


def test_overview_session_card_must_finish_before_weekly_can_succeed(tmp_path):
    outcome = run_js(
        tmp_path,
        EXTRACTOR_JS,
        {
            "body": "Usage Overview 5 hour usage limit Weekly limits 4 days until reset 94% remaining",
            "elements": [
                tab("Overview", True),
                {"tag": "div", "text": "Weekly limits 4 days until reset 94% remaining"},
            ],
        },
    )
    assert outcome["result"]["__retry_after_ms"] == 1200
    assert outcome["result"]["weekly"] is None


def test_overview_ancestor_cannot_lend_weekly_percent_to_session(tmp_path):
    outcome = run_js(
        tmp_path,
        EXTRACTOR_JS,
        {
            "body": "5 hour usage limit Weekly limits 4 days until reset 94% remaining",
            "elements": [
                tab("Overview", True),
                {"tag": "div", "text": "5 hour usage limit Weekly limits 4 days until reset 94% remaining"},
                {"tag": "div", "text": "5 hour usage limit"},
                {"tag": "div", "text": "Weekly limits 4 days until reset 94% remaining"},
            ],
        },
    )
    assert outcome["result"]["__retry_after_ms"] == 1200
    assert outcome["result"]["session"] is None
    assert outcome["result"]["weekly"] is None


def test_overview_ancestor_cannot_lend_session_percent_to_weekly(tmp_path):
    outcome = run_js(
        tmp_path,
        EXTRACTOR_JS,
        {
            "body": "5 hour usage limit Resets in 4 hours 20% used Weekly limits",
            "elements": [
                tab("Overview", True),
                {"tag": "div", "text": "5 hour usage limit Resets in 4 hours 20% used Weekly limits"},
                {"tag": "div", "text": "5 hour usage limit Resets in 4 hours 20% used"},
                {"tag": "div", "text": "Weekly limits"},
            ],
        },
    )
    assert outcome["result"]["__retry_after_ms"] == 1200
    assert outcome["result"]["session"] is None
    assert outcome["result"]["weekly"] is None


def test_selected_overview_history_idle_percent_is_not_ready(tmp_path):
    spec = {
        "body": "Usage history Weekly limits Period % of limit used Sep 21-26 0% used",
        "elements": [
            tab("Overview", True),
            {"tag": "section", "text": "Usage history Weekly limits Period % of limit used Sep 21-26 0% used"},
        ],
    }
    extracted = run_js(tmp_path, EXTRACTOR_JS, spec)
    assert extracted["result"]["__retry_after_ms"] == 1200
    assert extracted["result"]["weekly"] is None
    assert run_js(tmp_path, VERIFY_JS, spec)["result"] is False


def test_overview_click_guard_survives_repeated_extraction_on_same_document(tmp_path):
    outcome = run_js(
        tmp_path,
        EXTRACTOR_JS,
        {
            "repeat": 2,
            "body": "Usage history",
            "elements": [tab("Overview", False), tab("Analytics", True)],
        },
    )
    assert outcome["clicks"] == 1
    assert [item["__retry_reason"] for item in outcome["results"]] == [
        "selected overview tab",
        "waiting for Overview tab",
    ]


def test_verify_uses_same_card_detection_as_extractor(tmp_path):
    ready = {
        "body": "Usage Overview Weekly limits 4 days until reset 94% remaining",
        "elements": [tab("Overview", True), {"tag": "div", "text": "Weekly limits 4 days until reset 94% remaining"}],
    }
    bait = {"body": "Usage history Weekly limits Period % of limit used Sep 21-26 73.9%", "elements": [tab("Overview", True)]}
    assert run_js(tmp_path, VERIFY_JS, ready)["result"] is True
    assert run_js(tmp_path, VERIFY_JS, bait)["result"] is False


def test_legacy_dual_card_layout_remains_supported(tmp_path):
    outcome = run_js(
        tmp_path,
        EXTRACTOR_JS,
        {
            "body": "5 hour usage limit Resets in 4 hours 20% used Weekly usage limit Resets in 5 days 10 hours 30% used",
            "elements": [
                {"tag": "div", "text": "5 hour usage limit Resets in 4 hours 20% used"},
                {"tag": "div", "text": "Weekly usage limit Resets in 5 days 10 hours 30% used"},
            ],
        },
    )
    assert outcome["result"]["session"]["percent"] == 20
    assert outcome["result"]["weekly"]["percent"] == 30
    assert run_js(tmp_path, VERIFY_JS, {"body": "", "elements": [
        {"tag": "div", "text": "5 hour usage limit Resets in 4 hours 20% used"},
        {"tag": "div", "text": "Weekly usage limit Resets in 5 days 10 hours 30% used"},
    ]})["result"] is True


def test_legacy_shared_weekly_only_layout_is_verified_and_extracted(tmp_path):
    spec = {
        "body": "Shared agentic usage limit Weekly usage limit Resets in 4 days 94% remaining Credits remaining",
        "elements": [
            {"tag": "div", "text": "Weekly usage limit Resets in 4 days 94% remaining"},
        ],
    }
    outcome = run_js(tmp_path, EXTRACTOR_JS, spec)
    assert outcome["result"]["session"] is None
    assert outcome["result"]["weekly"]["percent"] == 94
    assert run_js(tmp_path, VERIFY_JS, spec)["result"] is True


def test_legacy_ancestor_does_not_cross_fill_partial_dual_layout(tmp_path):
    spec = {
        "body": "5 hour usage limit Resets in 4 hours 20% used Weekly usage limit",
        "elements": [
            {"tag": "div", "text": "5 hour usage limit Resets in 4 hours 20% used Weekly usage limit"},
            {"tag": "div", "text": "5 hour usage limit Resets in 4 hours 20% used"},
            {"tag": "div", "text": "Weekly usage limit"},
        ],
    }
    outcome = run_js(tmp_path, EXTRACTOR_JS, spec)
    assert outcome["result"]["session"]["percent"] == 20
    assert outcome["result"]["weekly"] is None
    assert run_js(tmp_path, VERIFY_JS, spec)["result"] is False


def test_legacy_shared_weekly_marker_does_not_hide_partial_session(tmp_path):
    spec = {
        "body": "Shared agentic usage limit 5 hour usage limit Weekly usage limit Resets in 4 days 94% remaining Credits remaining",
        "elements": [
            {"tag": "div", "text": "5 hour usage limit"},
            {"tag": "div", "text": "Weekly usage limit Resets in 4 days 94% remaining"},
        ],
    }
    outcome = run_js(tmp_path, EXTRACTOR_JS, spec)
    assert outcome["result"]["session"] is None
    assert outcome["result"]["weekly"]["percent"] == 94
    assert run_js(tmp_path, VERIFY_JS, spec)["result"] is False


@pytest.mark.parametrize("weekly_label", ["Weekly limits", "每週上限", "Weekly usage limit"])
@pytest.mark.parametrize("render_cards", [True, False])
def test_weekly_first_partial_card_cannot_borrow_session_in_either_fallback(
    tmp_path, weekly_label, render_cards
):
    overview = weekly_label != "Weekly usage limit"
    session = "5 hour usage limit Resets in 4 hours 20% used"
    body = f"{weekly_label} {session}"
    elements = [tab("Overview", True)] if overview else []
    if render_cards:
        elements += [
            {"tag": "section", "text": body},
            {"tag": "div", "text": weekly_label},
            {"tag": "div", "text": session},
        ]
    spec = {"body": body, "elements": elements}
    payload = run_js(tmp_path, EXTRACTOR_JS, spec)["result"]
    assert payload["weekly"] is None
    assert not payload.get("overview_ready")
    assert run_js(tmp_path, VERIFY_JS, spec)["result"] is False
    assert codex._build_snapshot(payload).status == SnapshotStatus.ERROR

    # An older extractor can supply only body text. It must not restore a
    # cross-card value that the current JavaScript correctly rejects.
    body_payload = {
        "url": codex.CODEX_USAGE_URL,
        "overview_confirmed": overview,
        "body_text": body,
    }
    assert codex._build_snapshot(body_payload).status == SnapshotStatus.ERROR


@pytest.mark.parametrize("layout", ["overview_weekly", "overview_dual", "legacy_dual"])
@pytest.mark.parametrize("render_cards", [True, False])
@pytest.mark.parametrize("quota_text", ["30% used", "remaining 70%"])
def test_absolute_resets_survive_extraction_and_body_fallback(
    tmp_path, monkeypatch, layout, render_cards, quota_text
):
    fixed_now = datetime(2026, 10, 4, 12, 0)
    monkeypatch.setattr(codex, "_parse_reset_text", partial(codex._parse_reset_text, now=fixed_now))
    overview = layout.startswith("overview")
    has_session = layout.endswith("dual")
    weekly_label = "Weekly limits" if overview else "Weekly usage limit"
    weekly = f"{weekly_label} Resets Mon 6:00 PM {quota_text}"
    cards = [weekly]
    if has_session:
        cards.insert(0, "5 hour usage limit Resets at 1:55 PM 20% used")
    elements = [tab("Overview", True)] if overview else []
    if render_cards:
        elements += [{"tag": "div", "text": card} for card in cards]
    spec = {"body": " ".join(cards), "elements": elements}
    payload = run_js(tmp_path, EXTRACTOR_JS, spec)["result"]
    assert payload["weekly"]["reset_text"] == "Mon 6:00 PM"
    if has_session:
        assert payload["session"]["reset_text"] == "1:55 PM"
    assert run_js(tmp_path, VERIFY_JS, spec)["result"] is True
    expected = [("Weekly", 30, datetime(2026, 10, 5, 18, 0))]
    if has_session:
        expected.insert(0, ("Session", 20, datetime(2026, 10, 4, 13, 55)))
    for candidate in (
        payload,
        {"url": codex.CODEX_USAGE_URL, "overview_confirmed": overview, "body_text": spec["body"]},
    ):
        snapshot = codex._build_snapshot(candidate)
        assert snapshot.status == SnapshotStatus.OK
        assert [(metric.label, metric.percent_used, metric.resets_at) for metric in snapshot.metrics] == expected
