<p align="center">
  <img src="src/aigauge/assets/aigaugeicon.png" alt="AI Gauge app icon" width="180" />
</p>

<h1 align="center">AI Gauge</h1>

<p align="center"><strong>Know your AI usage at a glance.</strong></p>

<p align="center">
  <a href="https://github.com/DraftingDreamer/ai-gauge/actions/workflows/test.yml"><img src="https://github.com/DraftingDreamer/ai-gauge/actions/workflows/test.yml/badge.svg" alt="Test status" /></a>
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-0078d4" alt="Windows, macOS, and Linux" />
  <img src="https://img.shields.io/badge/python-3.11%2B-3776ab" alt="Python 3.11+" />
  <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT license" />
</p>

This is the **DraftingDreamer fork** of [AI Gauge by John Pajak](https://github.com/jpajak/ai-gauge), maintained at [DraftingDreamer/ai-gauge](https://github.com/DraftingDreamer/ai-gauge). It retains the upstream project's MIT license and source attribution. Fork-specific additions are summarized here; see the [upstream project](https://github.com/jpajak/ai-gauge) for its original features and history.

| Fork addition | What it does |
| --- | --- |
| Antigravity quota | Reads local `agy /quota` output, supports executable selection and Gemini / Claude+GPT display groups, and stops polling when a response may have consumed tokens. |
| Reset announcements | Adds Codex Resets and Claude Resets tiles; Windows uses concurrent native toast notifications, with tray-balloon fallback. |
| Refresh status | Error labels show the cause and mark retained values as stale. |
| Codex Overview | Reads current quota from the Overview page in English and Traditional Chinese, includes weekly reset countdowns, and rejects Analytics history as current quota. |
| Claude sign-in | Shows a Sign in action for recognized sign-in redirects; based in part on changes by [innoscoutpro](https://github.com/innoscoutpro/ai-gauge/commits?author=innoscoutpro). |

AI Gauge is a compact desktop monitor for **Claude.ai**, **ChatGPT Codex**,
**Antigravity**, **OpenCode Go**, **GitHub Copilot**, and **OpenRouter**. It shows
usage limits, reset times, balances, and spend at a glance. Optional local
tracking estimates the API-equivalent cost of Claude Code and Codex activity on
this computer.

- **Windows / Linux** — always-on-top draggable frameless widget plus a system-tray icon.
- **macOS** — Stats-style menu-bar item (`● Cl 42% ● Cx 78% ● Co 15%`); the panel opens as a popover when you click it.

> **Requires Python 3.11+.** Secrets live in the OS-native credential store (Windows Credential Manager / DPAPI, macOS Keychain, Linux Secret Service). Auto-start uses the platform's standard mechanism (Windows Task Scheduler / LaunchAgent / `~/.config/autostart`).

Current version: **0.9.0**. See [CHANGELOG.md](CHANGELOG.md) for release notes.

AI Gauge is an independent open-source project and unofficial local desktop
utility. It is not affiliated with Anthropic, OpenAI, GitHub, Microsoft,
OpenRouter, or any other provider. Provider pages and APIs may change without
notice.

## Screenshots

**Windows / Linux** — always-on-top floating widget in full and compact modes:

<p align="center">
  <img src="docs/screenshots/win-panel-full.png" alt="AI Gauge full panel showing provider usage" width="320" />
  &nbsp;&nbsp;
  <img src="docs/screenshots/win-panel-compact.png" alt="AI Gauge collapsed pill mode" width="320" />
</p>

**macOS** — native menu-bar usage summary:

<p align="center">
  <img src="docs/screenshots/mac-menubar.png" alt="AI Gauge macOS menu-bar item showing provider usage" width="400" />
</p>

## Download

Pre-built binaries for each release are published on the [DraftingDreamer Releases page](https://github.com/DraftingDreamer/ai-gauge/releases). Pick the archive for your OS, extract, and run:

| OS      | Archive                              | Run                                |
| ------- | ------------------------------------ | ---------------------------------- |
| Windows | `ai-gauge-<version>-windows.zip`     | extract, run `ai-gauge.exe`        |
| macOS   | `ai-gauge-<version>-macos.tar.gz`    | extract, drag `ai-gauge.app` to Applications |
| Linux   | `ai-gauge-<version>-linux.tar.gz`    | extract, run `./ai-gauge/ai-gauge` |

SHA256 sums are published alongside each archive. Builds are unsigned - see the [first-launch warnings](#build-a-standalone-binary) section below for SmartScreen / Gatekeeper handling.

## Run from source

**Windows (PowerShell):**

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m aigauge
```

**macOS / Linux (bash):**

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -e .
./.venv/bin/python -m aigauge
```

On first launch the widget appears with enabled provider tiles. Claude and Codex use a **Sign in** or **Paste cookie** flow; OpenCode Go, GitHub Copilot, and OpenRouter are configured from Settings with API credentials. Open Settings to disable providers you don't use or to add more Claude, Codex, or OpenCode Go accounts.

## First-time setup per provider

| Provider           | Setup                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Claude.ai**      | **Sign in (recommended):** asks which installed Chrome-family browser to use, remembers that choice, supports Google and passkeys, and connects the resulting Claude session automatically. No cookie copying is required. **Paste cookie:** remains available as a recovery fallback. Add extra Claude subscriptions from **Settings → Claude**. |
| **ChatGPT Codex**  | Same as Claude — **Sign in** uses your chosen installed browser and automatically connects the ChatGPT session, including Google-linked and passkey accounts. **Paste cookie** remains available only as a fallback. Add extra Codex subscriptions from **Settings → Codex**. |
| **OpenCode Go**    | Sign in at <https://opencode.ai/auth> and copy an API key. In **Settings → OpenCode**, paste the key beside the subscription name. Each subscription has an independent key and tile. AI Gauge stores keys in the system credential store and reads Rolling, Weekly, and Monthly usage from the authenticated Go API. The shorter name **OpenCode** is used in the app. |
| **GitHub Copilot** | Create a **fine-grained PAT** at <https://github.com/settings/personal-access-tokens/new>. For personal plans, add **Account permissions → Plan → Read**. Paste into Settings; set your monthly AI credit allowance (Pro=1,500, Pro+=7,000, Max=20,000). If Copilot is billed through an organization, enter the billing org and use a token/account with org billing access and **Organization permissions → Administration → Read**. |
| **OpenRouter**     | Create an inference API key at <https://openrouter.ai/keys> and paste it into Settings. To show account balance and model activity, also create a management key at <https://openrouter.ai/settings/provisioning-keys>. Management keys cannot be used for inference; AI Gauge stores it separately and only uses it for OpenRouter management endpoints. Daily spend budget is optional.                                                    |
| **Antigravity**    | In **Settings → General**, enable **Antigravity**. AI Gauge runs the local `agy` CLI's `/quota` command; no account or API key is entered in AI Gauge. Leave **agy CLI** blank for auto-detection (`agy` on `PATH`, then `%LOCALAPPDATA%\agy\bin\agy.exe` on Windows), or select the executable. A missing file or a file not named `agy` is reported and not run. The tile can show Gemini and Claude+GPT usage, each with 5-hour and weekly limits; choose which groups to display in the Antigravity tab. AI Gauge disables `agy` background updates for its own calls and hides its console window; this does not affect updates when you run `agy` yourself. If a response indicates token use, or the result cannot confirm no use, polling stops until AI Gauge is restarted. |

### Multiple Claude / Codex / OpenCode Go accounts

Claude, Codex, and OpenCode Go can track more than one subscription at a time. Open the provider's Settings tab, click **Add another**, and give the account a short name. Use **Sign in** or **Paste cookie** for each Claude or Codex row; paste the matching API key into each OpenCode row. Default accounts display as `Claude`, `Codex`, or `OpenCode`; named accounts display as `Claude (Work)`, `Codex (Account 2)`, `OpenCode (Team)`, etc. Claude and Codex accounts keep separate browser sessions, while OpenCode accounts keep separate system-keychain entries.

The **General** tab controls provider groups. Enabling Claude, Codex, or OpenCode shows every configured account in that family. Any account can be removed from its provider tab, including the original account; the **Add another** button remains available when no accounts are configured. Every account has separate credentials, widget tile state, and history records.

Use **Clear sign-in** beside an account to remove its session from AI Gauge.
This clears both the OS-protected saved cookie and the account's live embedded
browser cookies. It does not revoke sessions in other browsers or devices; use
the provider's security settings when you need to sign out everywhere.

### Optional local usage and cost

Enable **Settings → Local usage** to estimate what Claude Code and Codex
activity on this computer would cost at API prices. AI Gauge stores token
counts, model names, and timestamps locally; nothing is uploaded and the
estimates are not charges.

### Optional reset announcements

Both reset tiles are off by default. Enable **Codex Resets** or **Claude Resets**
in **Settings → General**. These
third-party trackers are independent of OpenAI and Anthropic, and their AI
classification can mistake an ambiguous post for a completed reset; open the
linked original post to confirm. AI Gauge contacts each tracker no more than
once every 15 minutes, including after a failed request; if a tracker asks for
a longer wait, AI Gauge honors it. The sites receive your IP address and the
`ai-gauge/<version> (+https://github.com/DraftingDreamer/ai-gauge)` User-Agent.
Requests go to `https://codex-resets.com/api/v1/status` and
`https://claude-resets.com/api/resets`. The tiles show the latest event; ✕ hides
the tile until another entry arrives. Codex also shows an
AI-predicted **Watch** row, which is not an official announcement and does not
trigger notifications. Claude provisional events are marked in the tooltip;
Claude entries not marked as `reset` (including policy notices) are omitted.
AI Gauge only opens links supplied by the trackers when they use `http` or
`https`.
Choose reset notification
types in **Settings → Reset alerts**: Codex offers announced, landed, and
banked-reset alerts; Claude offers landed and banked-reset alerts. The first
event found after enabling a tracker is recorded without a notification.
[Data from Codex Resets](https://codex-resets.com) · [Data from Claude Resets](https://claude-resets.com)

Open **Usage details** to compare allowance use with estimated cost, including
views by model, day, and trend. Browser chats, cloud tasks, other computers,
and logs deleted before AI Gauge imports them are not included.

### How browser sign-in works

Google does not allow OAuth sign-in inside embedded browser controls, so AI
Gauge can open Chrome, Edge, Brave, or Chromium instead. On first use it asks
which one you want and remembers the choice; change it later under **Settings →
General → Sign-in browser**. The flow is local:

1. AI Gauge creates a new temporary browser profile containing none of your
   regular browser history, extensions, cookies, or saved accounts.
2. You sign in normally in that browser window, including with Google or a
   passkey.
3. AI Gauge watches the temporary browser through a random loopback-only
   debugging port and accepts cookies only for the selected provider:
   `claude.ai` or `chatgpt.com`.
4. The provider session is copied into that AI Gauge account's persistent
   browser profile and OS-protected secret storage. Google cookies and cookies
   for unrelated sites are ignored.
5. AI Gauge closes the temporary browser, deletes its temporary profile, and
   verifies that the provider's usage page is signed in.

The small AI Gauge window shown alongside the external browser is a status and
recovery dialog, not a second active browser. The embedded webview loads only
when you choose it. If the external browser closes before authentication, AI
Gauge returns to the browser choice instead of opening the fallback on its own.
In embedded mode, a recognized session is verified automatically; **I'm signed
in** remains available as a manual fallback.

Your everyday Chrome/Edge profile is never opened or inspected. The imported
provider session remains available across AI Gauge restarts, so sign-in only
needs to be repeated when the provider expires or revokes it. The embedded
browser and manual **Paste cookie** option remain available as recovery paths.

Sessions persist between runs under the per-OS app-data directory:

| OS      | App data                                  | Secrets backend                           |
| ------- | ----------------------------------------- | ----------------------------------------- |
| Windows | `%APPDATA%/ai-gauge/`                     | Credential Manager (GitHub PAT + OpenRouter keys) + DPAPI-encrypted `secrets.dat` (cookies, since the Credential Manager blob limit is too small for ChatGPT JWTs) |
| macOS   | `~/Library/Application Support/ai-gauge/` | Login Keychain                            |
| Linux   | `~/.config/ai-gauge/`                     | Secret Service (GNOME Keyring / KWallet)  |

AI Gauge does not include telemetry or a backend service. Provider requests
are made from the local app to the configured providers. See
[SECURITY.md](SECURITY.md) for security and privacy notes.

### Paste cookie (fallback)

If automatic browser sign-in cannot start or import the provider session, you
can still copy an existing Claude or Codex session cookie into the
app manually. This is a recovery path; Google-linked and passkey accounts
should work with the normal **Sign in** button.

1. Sign into the provider in **Chrome / Edge / Firefox** as you normally do.
2. For ChatGPT, press **F12** → **Network**, reload the page, click a
   `chatgpt.com` request, and copy the full **Request Headers → Cookie:** value.
   This includes split session cookies plus companion auth cookies such as
   `__Secure-oai-is`.
3. For Claude, press **F12** → **Network**, reload `https://claude.ai/new#settings/usage`,
   click a `claude.ai` request, and copy the full **Request Headers → Cookie:**
   value. It must include `sessionKey`.
4. In the app, open the matching provider tab in Settings, click **Paste cookie**, paste the header, and Save.

## Daily use

- **Windows / Linux:** drag the floating widget to move it and use the
  bottom-right grip to resize it. Collapse it to a compact pill or hide it in
  the system tray. Right-click the widget or tray icon for the full menu. On
  desktops without a system tray, right-click the widget instead.
- **macOS:** the menu-bar item shows the highest usage for each enabled
  provider or account. Click it to open the popover.
- Settings control providers, accounts, colors, window behavior, UI scale,
  refresh timing, and start-at-login.
- Auto-refresh runs every 5 minutes while usage is changing, then backs off to
  a maximum of 60 minutes by default.
- On Windows, reset alerts use native notifications in Notification Center;
  clicking one opens its original post in your browser, including after AI Gauge
  exits. Alerts that arrive together are shown at the same time. If native
  notifications fail, or on non-Windows systems, a system
  tray balloon is used when a Qt system tray is available. Balloons are spaced
  at least 8 seconds apart; clicking one opens the last balloon's post.
  Reset notifications are not shown in macOS menu-bar mode or on Linux
  without a system tray. Reset tiles still update in the macOS popover and the
  tray-less Linux floating widget.
  If balloon tips are turned off in Windows, the fallback balloons are not
  shown.
  AI Gauge registers its
  notification name and bundled icon under
  `HKCU\Software\Classes\AppUserModelId\AloeDesk.AIGauge` (`DisplayName` =
  `AI Gauge`, `IconUri` = the bundled icon path); you can delete this key after
  uninstalling.
- On refresh errors, tiles show the short cause; retained values are marked
  `<cause> · stale` (for example, `offline · stale` or `timeout · stale`), and
  errors without retained values show `error · <cause>`.

## Build a standalone binary

For most users the [pre-built downloads](#download) are easier — this section is for building locally or for maintainers cutting releases. The build machine needs Python 3.11+ and a `.venv` with `pip install -e .[dev]` already run. Windows builds also require PowerShell 7 (`pwsh`). The resulting binary does **not** require Python or PowerShell on the target machine.

| OS      | Command          | Output                       |
| ------- | ---------------- | ---------------------------- |
| Windows | `pwsh -File .\build.ps1` | `dist/ai-gauge/ai-gauge.exe` |
| macOS   | `./build.sh`     | `dist/ai-gauge.app`          |
| Linux   | `./build.sh`     | `dist/ai-gauge/ai-gauge`     |

Tagged commits matching `v*` run [the release workflow](.github/workflows/release.yml), which builds all three platforms and prepares a draft GitHub Release with SHA256 files. A separate maintainer-triggered test build uploads artifacts without creating a release. The maintainer checks the draft artifacts and isolated GUI/MCP smoke results before publishing; see [RELEASING.md](RELEASING.md). CI does not validate live provider accounts.

Bundles are ~150-200 MB because the Chromium runtime ships inside. User data still lives outside the bundle, under the per-OS app-data directory.

For a single-file binary (slower first launch), pass `-OneFile` (PowerShell) or `--onefile` (bash). On macOS the `.app` bundle is recommended over the single-file form.

**First-launch warnings on signed-OS-bundle systems** - release artifacts are unsigned:

- **Windows:** SmartScreen -> "More info" -> "Run anyway". Windows builds include product/version metadata, but unsigned low-prevalence binaries can still trigger SmartScreen or Microsoft Defender reputation warnings.
- **macOS:** Gatekeeper blocks on first launch. Either right-click the `.app` → Open the first time, or run `xattr -dr com.apple.quarantine ai-gauge.app` once.
- **Linux:** no signing layer; just make `ai-gauge` executable if it isn't already.

See [RELEASING.md](RELEASING.md) for maintainer release steps.

## Tests

Tests need the dev extras, which the run-from-source install above omits:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .[dev]     # Windows
./.venv/bin/python -m pip install -e '.[dev]'           # macOS / Linux
```

```powershell
.\.venv\Scripts\python.exe -m pytest    # Windows
./.venv/bin/python -m pytest            # macOS / Linux
```

The automated suite covers provider parsing, configuration, UI behavior,
local usage tracking, MCP guards, credential storage, and platform
integration. Live Claude and Codex browser sessions are validated manually.

## MCP usage guard

AI Gauge includes an optional local stdio MCP server that lets tools inspect
sanitized usage and cooperatively pause costly work. Enable it under
**Settings → MCP**, configure an optional pause percentage, and bind each MCP
client to its account:

```text
ai-gauge-mcp --account-id codex-work
```

Source installations also need `pip install -e '.[mcp]'`. See
[docs/mcp.md](docs/mcp.md) for client instructions, packaged-helper paths,
macOS quarantine handling, and the guard's security model.

## Contributing

Bug reports, provider-layout fixes, and PRs are welcome. Open fork-specific
issues on the [DraftingDreamer issue tracker](https://github.com/DraftingDreamer/ai-gauge/issues).
See [CONTRIBUTING.md](CONTRIBUTING.md) for environment setup, test commands,
and the issue templates to use.

## Notes / limitations

- Reset-announcement tiles have no percentage and are omitted from the macOS
  menu-bar summary.
- Antigravity usage, reset tiles, and native notifications have been tested on
  Windows 11 only; macOS and Linux are untested.
- **Why does Sign in open a separate Chrome-family window?** Google blocks OAuth in embedded user-agents, while Chrome's App-Bound Encryption prevents AI Gauge from reading an existing everyday browser profile. AI Gauge therefore opens a fresh temporary browser profile, receives only the selected provider's cookies through Chrome's loopback debugging interface, imports them into the app, and deletes the temporary profile.
- **Claude / Codex layouts may change.** If a browser-backed provider tile shows "error" after an upstream UI update, its page-extractor JS under `src/aigauge/providers/` may need adjusting — the rest of the app keeps working.
- **Remote desktops and GPU-less sessions need one caveat.** The gauge is plain Qt Widgets and runs anywhere, including over RDP/XRDP and on machines with no GPU. Claude and Codex are read by driving an embedded Chromium, which needs an OpenGL context; a session offering neither GLX nor EGL cannot provide one. In that case those tiles report that they need a browser, while OpenCode Go, GitHub Copilot, and OpenRouter use API credentials and work normally. Most Linux desktops supply software GL through Mesa, so this only bites on bare X servers and some remote sessions. If AI Gauge misjudges your session, set `AIGAUGE_FORCE_WEBENGINE=1` to skip the check.
- The Copilot REST endpoint returns the _current calendar month_ of billing usage. The widget tracks gross AI credits consumed against the included allowance; net quantity/amount is only the billable overage. Reset is computed as the 1st of the next month. GitHub does not currently expose a reliable personal-plan allowance field, so Settings uses a plan dropdown with a Custom fallback. Annual/request-based accounts are handled with a legacy premium-request fallback.
- **Copilot usage lags upstream.** The Copilot REST endpoint updates noticeably slower than Claude or Codex — credit counts can take hours to reflect recent activity. The widget shows the most recent value GitHub returns; treat the Copilot tile as a trailing indicator, not real-time.
- **Copilot AI credits.** GitHub moved Copilot from per-request quotas to token-based AI credits. Code completions and next edit suggestions remain included for paid plans, while Chat, CLI, cloud agent, Spaces, Spark, and third-party coding agents consume AI credits. The app shows the credit usage GitHub returns; if your account is org-billed, enter the billing organization so AI Gauge reads the organization billing pool.
- **OpenRouter uses two key types.** The inference key is used for `/key` spend data. The management key is required for `/credits` account balance and `/activity` model history. Without a management key, AI Gauge still shows key-level spend but cannot show balance or model activity.
- **OpenRouter time windows are UTC.** Today/month spend come from OpenRouter's current UTC day and month fields. Model activity comes from OpenRouter's default `/activity` history window: the last 30 completed UTC days, excluding the current UTC day.
