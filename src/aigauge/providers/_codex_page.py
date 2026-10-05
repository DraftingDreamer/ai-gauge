"""Qt-free page scripts and URL for the Codex usage view."""

CODEX_USAGE_URL = "https://chatgpt.com/settings/usage"

_PAGE_CORE_JS = r"""
function visibleText(el) {
  return ((el && (el.innerText || el.textContent)) || '').replace(/\s+/g, ' ').trim();
}

function isVisible(el) {
  for (let node = el; node && node !== document; node = node.parentElement) {
    if (node.hidden || node.getAttribute('aria-hidden') === 'true') return false;
    const style = String(node.getAttribute('style') || '').toLowerCase();
    if (/display\s*:\s*none|visibility\s*:\s*hidden/.test(style)) return false;
    if (typeof getComputedStyle === 'function') {
      const computed = getComputedStyle(node);
      if (computed.display === 'none' || computed.visibility === 'hidden') return false;
    }
  }
  return true;
}

function isUsageRoute() {
  return location.hostname === 'chatgpt.com' &&
    (location.pathname === '/settings/usage' ||
     location.pathname === '/codex/cloud/settings/analytics');
}

function isSecurityPage(bodyText) {
  const text = (document.title + ' ' + bodyText).toLowerCase();
  return /verify you are human|verifying you are human|security verification|checking if the site connection is secure|needs to review the security of your connection|enable javascript and cookies to continue|performance & security by cloudflare/.test(text) ||
    (/just a moment/.test(document.title.toLowerCase()) && /cloudflare/.test(text));
}

function isLoggedOut(bodyText) {
  const path = location.pathname.toLowerCase();
  const loginLink = Array.from(document.querySelectorAll('a[href]'))
    .some(el => isVisible(el) && /\/(?:auth\/)?login(?:\/|$)/i.test(el.getAttribute('href') || ''));
  const usagePresent = /usage overview|weekly limits|weekly usage limit|5 hour usage limit|personal usage|概覽|每週上限/i.test(bodyText);
  return /\/(?:auth\/)?login(?:\/|$)|\/logout(?:\/|$)/.test(path) ||
    !!document.title.toLowerCase().match(/sign in|log in/) || loginLink ||
    (/\b(?:log in|sign in)\b/i.test(bodyText) && !usagePresent);
}

function findTab(label) {
  const elements = Array.from(document.querySelectorAll('button,a,[role="tab"],[role="button"]'));
  return elements.find(el => isVisible(el) && visibleText(el).toLowerCase() === label.toLowerCase()) || null;
}

function tabSelected(target) {
  return target.getAttribute('aria-selected') === 'true' ||
    target.getAttribute('aria-pressed') === 'true' ||
    target.getAttribute('data-state') === 'active' ||
    /\bactive\b|\bselected\b/.test(String(target.className || ''));
}

function maybeSelectOverview(bodyText) {
  const overview = findTab('Overview') || findTab('概覽');
  if (!overview) return '';
  if (tabSelected(overview)) return '';
  // The old analytics route has no quota card. The Overview tab is the only
  // safe in-page transition; never click a heading or a hidden tab.
  if (document.__aigaugeCodexOverviewClicked) return 'waiting for Overview tab';
  document.__aigaugeCodexOverviewClicked = true;
  overview.click();
  return 'selected overview tab';
}

function parseQuota(text, requireReset) {
  const percent = text.match(/(?:^|[^\d.+-])(\d+(?:\.\d+)?)\s*%/);
  if (!percent) return null;
  const value = Number(percent[1]);
  if (!Number.isFinite(value) || value < 0 || value > 100) return null;
  const kind = /\b(?:remaining|left)\b|剩餘|尚餘/i.test(text) ? 'remaining' :
    (/\bused\b|已用|已使用/i.test(text) ? 'used' : 'unknown');
  if (kind === 'unknown') return null;
  const relativePattern = /\d+\s*(?:days?|d|天)(?:\s*\d+\s*(?:hours?|hrs?|h|小時|小时))?(?:\s*\d+\s*(?:minutes?|mins?|m|分鐘|分钟))?|\d+\s*(?:hours?|hrs?|h|小時|小时)(?:\s*\d+\s*(?:minutes?|mins?|m|分鐘|分钟))?|\d+\s*(?:minutes?|mins?|m|分鐘|分钟)/i;
  const reset = text.match(/(?:resets?\s+(?:(?:at|on|in)\s+)?|(?:until|before)\s+(?:it\s+)?resets?\s*|(?:後|於)\s*(?:重設|重置)|(?:重設|重置)\s*(?:於|倒數)?\s*)(.{1,100})/i);
  const resetPrefix = text.match(/(.+?)(?:until\s+reset|before\s+(?:it\s+)?reset|後\s*重設|後\s*重置)/i);
  const resetValue = resetPrefix ? resetPrefix[1].slice(-120) : (reset ? reset[1] : '');
  const relative = resetValue.match(relativePattern);
  const resetPresent = !!reset || !!resetPrefix || /\breset(?:s)?\b|重設|重置/i.test(text);
  const idleQuota = (kind === 'remaining' && value === 100) ||
    (kind === 'used' && value === 0) || /starts? when (?:you )?use|開始使用/i.test(text);
  if (requireReset && !resetPresent && !idleQuota) return null;
  let resetText = relative ? relative[0] : (reset ? reset[1].trim() : null);
  // Absolute reset times can precede the percentage in the same card.
  // Remove the complete quota token, not just its direction word.
  if (resetText) resetText = resetText.split(/\s*(?:\d+(?:\.\d+)?\s*%|\b(?:remaining|left|used)\b|已使用|已用|剩餘|尚餘)/i)[0].trim() || null;
  return { raw: text.slice(0, 400), percent: value, kind, reset_text: resetText };
}

function isHistoryText(text) {
  return /usage history|plan usage history|使用歷史|(?:^|\s)period(?:\s|$)|期間\s*%|%\s*of\s*(?:the\s*)?limit\s*used/i.test(text);
}

function findQuotaCard(labels, requireReset, rejectLabels) {
  const elements = Array.from(document.querySelectorAll('article,section,[role="group"],div,li'));
  const candidates = [];
  for (const el of elements) {
    if (!isVisible(el)) continue;
    const text = visibleText(el);
    if (!text || text.length > 650 || !labels.some(label => text.toLowerCase().includes(label.toLowerCase()))) continue;
    if (isHistoryText(text)) continue;
    if ((rejectLabels || []).some(label => text.toLowerCase().includes(label.toLowerCase()))) continue;
    const quota = parseQuota(text, requireReset);
    if (quota) candidates.push({ el, text, quota });
  }
  candidates.sort((a, b) => a.text.length - b.text.length);
  return candidates.length ? candidates[0].quota : null;
}

function findBodyQuota(bodyText, labels, stopLabels, requireReset) {
  const text = bodyText.replace(/\s+/g, ' ').trim();
  const lower = text.toLowerCase();
  // Body fallback must respect every quota boundary in either card order.
  const quotaLabels = ['5 hour usage limit', 'weekly usage limit', 'weekly limits', 'weekly limit', '每週上限'];
  const matches = [];
  for (const label of labels) {
    const re = new RegExp(label, 'ig');
    let match;
    while ((match = re.exec(text)) !== null) {
      const start = match.index;
      let end = Math.min(text.length, start + 650);
      for (const next of [...stopLabels, ...quotaLabels]) {
        const at = lower.indexOf(next.toLowerCase(), start + match[0].length);
        if (at >= 0) end = Math.min(end, at);
      }
      const chunk = text.slice(start, end);
      if (isHistoryText(chunk)) continue;
      const quota = parseQuota(chunk, requireReset);
      if (quota) matches.push({ start, length: chunk.length, quota });
    }
  }
  matches.sort((a, b) => a.length - b.length);
  return matches.length ? matches[0].quota : null;
}

function getCodexPageState() {
  const bodyText = visibleText(document.body);
  if (!isUsageRoute()) return { type: 'out_of_scope', bodyText };
  if (isSecurityPage(bodyText)) return { type: 'security', bodyText };
  if (isLoggedOut(bodyText)) return { type: 'logged_out', bodyText };

  const overviewTab = findTab('Overview') || findTab('概覽');
  const overviewHeading = /usage overview|用量概覽/i.test(bodyText) && !/usage history|使用歷史/i.test(bodyText);
  const selectedOverview = maybeSelectOverview(bodyText);
  if (selectedOverview) return { type: 'retry', reason: selectedOverview, bodyText };
  const overviewConfirmed = !!(overviewTab && tabSelected(overviewTab)) || (!overviewTab && overviewHeading);

  if (overviewConfirmed) {
    const sessionLabels = ['5 hour usage limit'];
    const weeklyLabels = ['weekly limits', 'weekly limit', '每週上限'];
    const weekly = findQuotaCard(weeklyLabels, true, sessionLabels) ||
      findBodyQuota(bodyText, ['Weekly limits?', '每週上限'],
        ['plan usage history', 'usage history', 'analytics', 'period', 'tasks', 'subagents', '使用歷史', '分析', '期間', '每日使用量'], true);
    const sessionPresent = /5 hour usage limit/i.test(bodyText);
    const session = sessionPresent ? (findQuotaCard(sessionLabels, false, weeklyLabels) ||
      findBodyQuota(bodyText, ['5 hour usage limit'], ['weekly limits', 'weekly limit', 'weekly usage limit'], false)) : null;
    return { type: weekly && (!sessionPresent || session) ? 'overview_ready' : 'overview_loading', weekly, session, sessionPresent, bodyText };
  }

  const legacySessionLabels = ['5 hour usage limit'];
  const legacyWeeklyLabels = ['weekly usage limit'];
  const session = findQuotaCard(legacySessionLabels, false, legacyWeeklyLabels) ||
    findBodyQuota(bodyText, ['5 hour usage limit'], ['weekly usage limit'], false);
  const weekly = findQuotaCard(legacyWeeklyLabels, false, legacySessionLabels) ||
    findBodyQuota(bodyText, ['weekly usage limit'], ['personal usage', 'team usage'], false);
  if (session && weekly) return { type: 'legacy_ready', session, weekly, bodyText };
  if (weekly && !/5 hour usage limit/i.test(bodyText) &&
      /shared agentic usage limit|credits remaining|usage breakdown/i.test(bodyText)) {
    return { type: 'legacy_ready', session: null, weekly, bodyText };
  }

  // A classic personal usage page can be partially hydrated. Only click its
  // actual selected/available tab once; headings are never treated as buttons.
  const personal = findTab('Personal usage');
  if (personal && !tabSelected(personal) && !/5 hour usage limit|weekly usage limit/i.test(bodyText)) {
    personal.click();
    return { type: 'retry', reason: 'selected personal usage tab', bodyText };
  }
  return { type: 'legacy_partial', session, weekly, bodyText };
}
"""

EXTRACTOR_JS = "(() => {\n" + _PAGE_CORE_JS + r"""
  const state = getCodexPageState();
  const base = {
    url: location.href,
    title: document.title,
    body_text: state.bodyText.slice(0, 2000),
  };
  if (state.type === 'retry' || state.type === 'overview_loading') {
    return { ...base, __retry_after_ms: 1200, __retry_reason: state.reason || 'waiting for Overview quota',
      logged_out: false, session: null, weekly: null, overview_confirmed: false };
  }
  if (state.type === 'security') return { ...base, logged_out: false, security_verification: true, session: null, weekly: null };
  if (state.type === 'logged_out' || state.type === 'out_of_scope') return { ...base, logged_out: true, session: null, weekly: null };
  return {
    ...base,
    logged_out: false,
    session: state.session || null,
    weekly: state.weekly || null,
    overview_confirmed: state.type === 'overview_ready',
    overview_ready: state.type === 'overview_ready',
    has_percent_text: /%/.test(state.bodyText),
    has_usage_text: /usage/i.test(state.bodyText),
  };
})()"""

VERIFY_JS = "(() => {\n" + _PAGE_CORE_JS + r"""
  const state = getCodexPageState();
  return state.type === 'overview_ready' || state.type === 'legacy_ready';
})()"""
