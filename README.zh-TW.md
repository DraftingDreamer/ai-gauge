<p align="center">
  <img src="src/aigauge/assets/aigaugeicon.png" alt="AI Gauge 應用程式圖示" width="180" />
</p>

<h1 align="center">AI Gauge</h1>

<p align="center"><strong>AI 用量，一眼掌握。</strong></p>

<p align="center">
  <a href="README.md">English</a> · <strong>繁體中文</strong> · <a href="README.zh-CN.md">简体中文</a>
</p>

<p align="center">
  <a href="https://github.com/DraftingDreamer/ai-gauge/actions/workflows/test.yml"><img src="https://github.com/DraftingDreamer/ai-gauge/actions/workflows/test.yml/badge.svg" alt="測試狀態" /></a>
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-0078d4" alt="支援 Windows、macOS 與 Linux" />
  <img src="https://img.shields.io/badge/python-3.11%2B-3776ab" alt="Python 3.11+" />
  <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT 授權" />
</p>

這是 [John Pajak 的 AI Gauge](https://github.com/jpajak/ai-gauge) 的 **DraftingDreamer 分支版本（fork）**，維護於 [DraftingDreamer/ai-gauge](https://github.com/DraftingDreamer/ai-gauge)。本分支保留上游專案的 MIT 授權與原始碼出處標示。此處僅摘要分支專屬的新增功能；上游專案的原有功能與沿革，請參閱[上游專案](https://github.com/jpajak/ai-gauge)。

| 分支新增功能 | 說明 |
| --- | --- |
| Antigravity 額度 | 讀取本機 `agy /quota` 的輸出，支援選擇執行檔，以及 Gemini／Claude+GPT 顯示群組；當某次回應可能已消耗 token 時，會停止輪詢。 |
| 重置公告 | 新增 Codex Resets 與 Claude Resets 磚塊；Windows 上使用並行的原生 Toast 通知，並以系統匣氣泡通知作為備援。 |
| 重新整理狀態 | 錯誤標籤會顯示原因，並將保留的數值標示為過期（stale）。 |
| Codex 總覽 | 從總覽頁面讀取目前額度（支援英文與繁體中文介面），包含每週重置倒數，並拒絕將 Analytics 歷史資料誤判為目前額度。 |
| Claude 登入 | 偵測到可辨識的登入重新導向時，顯示「Sign in」操作；部分內容改編自 [innoscoutpro](https://github.com/innoscoutpro/ai-gauge/commits?author=innoscoutpro) 的變更。 |

AI Gauge 是一款精巧的桌面監控工具，支援 **Claude.ai**、**ChatGPT Codex**、
**Antigravity**、**OpenCode Go**、**GitHub Copilot** 與 **OpenRouter**，
讓您一眼掌握用量上限、重置時間、餘額與花費。另可選擇啟用本機追蹤功能，
估算本機上 Claude Code 與 Codex 活動以 API 計價的等值費用。

- **Windows / Linux** — 永遠置頂、可拖曳的無邊框小工具，外加系統匣圖示。
- **macOS** — 類似 Stats 的選單列項目（`● Cl 42% ● Cx 78% ● Co 15%`）；點擊後，面板會以彈出視窗（popover）的形式開啟。

> **需要 Python 3.11 以上版本。** 機密資料存放於作業系統原生的憑證儲存區（Windows 認證管理員／DPAPI、macOS 鑰匙圈、Linux Secret Service）。開機自動啟動採用各平台的標準機制（Windows 工作排程器／LaunchAgent／`~/.config/autostart`）。

目前版本：**0.9.0**。發行說明請見 [CHANGELOG.md](CHANGELOG.md)。

AI Gauge 是獨立的開源專案，屬於非官方的本機桌面小工具，與 Anthropic、OpenAI、GitHub、Microsoft、OpenRouter 或任何其他服務供應商皆無隸屬關係。各供應商的頁面與 API 可能隨時異動，恕不另行通知。

## 螢幕截圖

**DraftingDreamer 分支 0.9.0 — Windows**

<p align="center">
  <img src="docs/screenshots/fork-0.9.0-windows.png" alt="Windows 上的 AI Gauge 0.9.0，顯示 Claude 與 Codex 用量、Antigravity 額度，以及 Codex 與 Claude 重置公告" width="520" />
</p>

擷取自執行中的 Windows 發行版本。用量數值為擷取當下的狀態。

**上游介面範例 — Windows / Linux** — 永遠置頂的浮動小工具，分為完整與精簡模式：

<p align="center">
  <img src="docs/screenshots/win-panel-full.png" alt="AI Gauge 完整面板，顯示各供應商的用量" width="320" />
  &nbsp;&nbsp;
  <img src="docs/screenshots/win-panel-compact.png" alt="AI Gauge 收合的膠囊模式" width="320" />
</p>

**上游介面範例 — macOS** — 原生選單列用量摘要：

<p align="center">
  <img src="docs/screenshots/mac-menubar.png" alt="AI Gauge macOS 選單列項目，顯示各供應商的用量" width="400" />
</p>

## 下載

每個版本的預先建置執行檔都發布在 [DraftingDreamer Releases 頁面](https://github.com/DraftingDreamer/ai-gauge/releases)。請選擇對應您作業系統的壓縮檔，解壓縮後即可執行：

| 作業系統 | 壓縮檔                               | 執行方式                           |
| ------- | ------------------------------------ | ---------------------------------- |
| Windows | `ai-gauge-<version>-windows.zip`     | 解壓縮後執行 `ai-gauge.exe`        |
| macOS   | `ai-gauge-<version>-macos.tar.gz`    | 解壓縮後，將 `ai-gauge.app` 拖曳至「應用程式」資料夾 |
| Linux   | `ai-gauge-<version>-linux.tar.gz`    | 解壓縮後執行 `./ai-gauge/ai-gauge` |

每個壓縮檔都附有 SHA256 雜湊值。執行檔未經數位簽章，關於 SmartScreen／Gatekeeper 的處理方式，請參閱下方[首次啟動警告](#建置獨立執行檔)一節。

## 從原始碼執行

**Windows（PowerShell）：**

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m aigauge
```

**macOS / Linux（bash）：**

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -e .
./.venv/bin/python -m aigauge
```

首次啟動時，小工具會顯示已啟用的供應商磚塊。Claude 與 Codex 使用 **Sign in**（登入）或 **Paste cookie**（貼上 Cookie）流程；OpenCode Go、GitHub Copilot 與 OpenRouter 則須在「設定」中以 API 憑證進行設定。您可以開啟「設定」停用不使用的供應商，或新增更多 Claude、Codex 或 OpenCode Go 帳號。

## 各供應商的首次設定

| 供應商             | 設定方式 |
| ------------------ | -------- |
| **Claude.ai**      | **Sign in（建議）：** 會詢問要使用哪一個已安裝的 Chrome 系列瀏覽器並記住您的選擇，支援 Google 與通行密鑰（passkey），並自動連接所取得的 Claude 工作階段，無須複製 Cookie。**Paste cookie：** 仍保留作為復原用的備援方式。如需新增其他 Claude 訂閱，請至 **設定 → Claude**。 |
| **ChatGPT Codex**  | 與 Claude 相同 — **Sign in** 會使用您選擇的已安裝瀏覽器，並自動連接 ChatGPT 工作階段，包括綁定 Google 與使用通行密鑰的帳號。**Paste cookie** 僅作為備援。如需新增其他 Codex 訂閱，請至 **設定 → Codex**。 |
| **OpenCode Go**    | 前往 <https://opencode.ai/auth> 登入並複製 API 金鑰。在 **設定 → OpenCode** 中，將金鑰貼在訂閱名稱旁。每個訂閱都有獨立的金鑰與磚塊。AI Gauge 會將金鑰存放於系統憑證儲存區，並透過已驗證的 Go API 讀取 Rolling、Weekly 與 Monthly 用量。應用程式內使用較短的名稱 **OpenCode**。 |
| **GitHub Copilot** | 至 <https://github.com/settings/personal-access-tokens/new> 建立 **fine-grained PAT**（細粒度個人存取權杖）。個人方案請加上 **Account permissions → Plan → Read**。將其貼入「設定」，並設定您每月的 AI 點數額度（Pro=1,500、Pro+=7,000、Max=20,000）。若 Copilot 是透過組織計費，請填入計費組織，並使用具備組織計費存取權的權杖／帳號，以及 **Organization permissions → Administration → Read**。 |
| **OpenRouter**     | 至 <https://openrouter.ai/keys> 建立推論用（inference）API 金鑰，並貼入「設定」。若要顯示帳戶餘額與模型活動，另請至 <https://openrouter.ai/settings/provisioning-keys> 建立管理金鑰（management key）。管理金鑰無法用於推論；AI Gauge 會將其另外儲存，且僅用於 OpenRouter 的管理端點。每日花費預算為選填。 |
| **Antigravity**    | 在 **設定 → General** 中啟用 **Antigravity**。AI Gauge 會執行本機 `agy` CLI 的 `/quota` 指令；無須在 AI Gauge 中輸入帳號或 API 金鑰。**agy CLI** 欄位留空即可自動偵測（先找 `PATH` 中的 `agy`，Windows 上再找 `%LOCALAPPDATA%\agy\bin\agy.exe`），您也可以自行選擇執行檔。若檔案不存在，或檔名不是 `agy`，系統會回報錯誤且不會執行。磚塊可顯示 Gemini 與 Claude+GPT 的用量，各有 5 小時與每週上限；請在 Antigravity 分頁選擇要顯示的群組。AI Gauge 在自行呼叫 `agy` 時會停用其背景更新並隱藏其主控台視窗；這不會影響您自行執行 `agy` 時的更新。若回應顯示有 token 消耗，或結果無法確認未消耗，輪詢會停止，直到重新啟動 AI Gauge。 |

### 多個 Claude / Codex / OpenCode Go 帳號

Claude、Codex 與 OpenCode Go 都可以同時追蹤多個訂閱。開啟該供應商的「設定」分頁，點選 **Add another**（新增其他帳號），並為帳號取一個簡短的名稱。每個 Claude 或 Codex 項目請使用 **Sign in** 或 **Paste cookie**；每個 OpenCode 項目則貼上對應的 API 金鑰。預設帳號顯示為 `Claude`、`Codex` 或 `OpenCode`；具名帳號則顯示為 `Claude (Work)`、`Codex (Account 2)`、`OpenCode (Team)` 等。Claude 與 Codex 帳號各自保有獨立的瀏覽器工作階段，OpenCode 帳號則各自使用獨立的系統鑰匙圈項目。

**General**（一般）分頁負責控制供應商群組。啟用 Claude、Codex 或 OpenCode 後，會顯示該系列中所有已設定的帳號。任何帳號（包括最初的帳號）都可以從其供應商分頁中移除；當尚未設定任何帳號時，**Add another** 按鈕仍然可用。每個帳號都有各自獨立的憑證、小工具磚塊狀態與歷史紀錄。

使用帳號旁的 **Clear sign-in**（清除登入）可從 AI Gauge 移除該帳號的工作階段。
這會同時清除受作業系統保護的已儲存 Cookie，以及該帳號內嵌瀏覽器中的即時 Cookie。
它不會撤銷其他瀏覽器或裝置上的工作階段；若需要在所有地方登出，請使用供應商的安全性設定。

### 選用：本機用量與費用

啟用 **設定 → Local usage**（本機用量），即可估算本機上 Claude Code 與 Codex
的活動若以 API 價格計算會花費多少。AI Gauge 會將 token 數量、模型名稱與時間戳記
儲存在本機；不會上傳任何資料，且這些估算值並非實際收費。

### 選用：重置公告

兩個重置磚塊預設皆為關閉。請在 **設定 → General** 中啟用 **Codex Resets** 或 **Claude Resets**。這些
第三方追蹤服務獨立於 OpenAI 與 Anthropic，其 AI
分類可能會將意思不明確的貼文誤判為已完成的重置；請開啟所附的原始貼文加以確認。AI Gauge 對每個追蹤服務
最多每 15 分鐘連線一次（請求失敗後亦同）；若追蹤服務要求更長的等待時間，AI Gauge 會遵從。這些網站會收到您的 IP 位址，以及
`ai-gauge/<version> (+https://github.com/DraftingDreamer/ai-gauge)` 這個 User-Agent。
請求會送往 `https://codex-resets.com/api/v1/status` 與
`https://claude-resets.com/api/resets`。磚塊會顯示最新事件；按下 ✕ 會隱藏
該磚塊，直到出現新的項目。Codex 另外會顯示一列
由 AI 預測的 **Watch**（觀察）資訊，它不是官方公告，也不會
觸發通知。Claude 的暫定事件會在提示文字中標示；
未標記為 `reset` 的 Claude 項目（包括政策公告）會被省略。
AI Gauge 僅會開啟追蹤服務所提供且使用 `http` 或
`https` 的連結。
請在 **設定 → Reset alerts**（重置提醒）中選擇重置通知
類型：Codex 提供已公告（announced）、已生效（landed）及
已存入（banked）重置提醒；Claude 提供已生效與已存入重置提醒。啟用追蹤服務後找到的第一個
事件只會被記錄，不會發出通知。
[資料來源：Codex Resets](https://codex-resets.com) · [資料來源：Claude Resets](https://claude-resets.com)

開啟 **Usage details**（用量詳情），即可比較額度使用量與估算費用，
並可依模型、日期與趨勢檢視。瀏覽器聊天、雲端任務、其他電腦，
以及在 AI Gauge 匯入前已刪除的紀錄，皆不包含在內。

### 瀏覽器登入的運作方式

Google 不允許在內嵌瀏覽器控制項內進行 OAuth 登入，因此 AI
Gauge 會改為開啟 Chrome、Edge、Brave 或 Chromium。首次使用時會詢問
您要用哪一個並記住選擇；之後可在 **設定 →
General → Sign-in browser**（登入用瀏覽器）中變更。整個流程皆在本機進行：

1. AI Gauge 會建立一個全新的暫時性瀏覽器設定檔，其中不含您
   平常使用的瀏覽器的任何瀏覽紀錄、擴充功能、Cookie 或已儲存的帳號。
2. 您在該瀏覽器視窗中照常登入，包括使用 Google 或
   通行密鑰。
3. AI Gauge 透過隨機產生、僅限本機回送（loopback）的
   偵錯連接埠監看該暫時性瀏覽器，並且只接受所選供應商的 Cookie：
   `claude.ai` 或 `chatgpt.com`。
4. 供應商的工作階段會被複製到該 AI Gauge 帳號的持久性
   瀏覽器設定檔與受作業系統保護的機密儲存區。Google 的 Cookie 與
   不相關網站的 Cookie 皆會被忽略。
5. AI Gauge 會關閉暫時性瀏覽器、刪除其暫時性設定檔，並
   驗證供應商的用量頁面已處於登入狀態。

與外部瀏覽器並列顯示的小型 AI Gauge 視窗，是狀態與
復原用的對話方塊，而不是第二個作用中的瀏覽器。內嵌 WebView 僅在
您選擇時才會載入。若外部瀏覽器在驗證完成前被關閉，AI
Gauge 會回到瀏覽器選擇畫面，而不會自行開啟備援方式。
在內嵌模式下，系統會自動驗證已辨識的工作階段；**I'm signed
in**（我已登入）仍可作為手動備援。

您日常使用的 Chrome／Edge 設定檔絕不會被開啟或檢視。匯入的
供應商工作階段在 AI Gauge 重新啟動後仍然有效，因此只有在供應商讓其過期或撤銷時，
才需要重新登入。內嵌
瀏覽器與手動的 **Paste cookie** 選項仍可作為復原途徑。

工作階段會在多次執行之間保留，存放於各作業系統的應用程式資料目錄：

| 作業系統 | 應用程式資料                              | 機密儲存後端                              |
| ------- | ----------------------------------------- | ----------------------------------------- |
| Windows | `%APPDATA%/ai-gauge/`                     | 認證管理員（GitHub PAT + OpenRouter 金鑰）＋以 DPAPI 加密的 `secrets.dat`（用於 Cookie，因為認證管理員的資料大小上限對 ChatGPT 的 JWT 而言太小） |
| macOS   | `~/Library/Application Support/ai-gauge/` | 登入鑰匙圈                                |
| Linux   | `~/.config/ai-gauge/`                     | Secret Service（GNOME Keyring / KWallet） |

AI Gauge 不含遙測功能，也沒有後端服務。對供應商的請求
皆由本機應用程式直接向所設定的供應商發出。安全性與隱私權相關說明，請參閱
[SECURITY.md](SECURITY.md)。

### Paste cookie（備援方式）

若自動瀏覽器登入無法啟動，或無法匯入供應商的工作階段，
您仍可手動將現有的 Claude 或 Codex 工作階段 Cookie 複製到
應用程式中。這是一種復原途徑；綁定 Google 與使用通行密鑰的帳號
應可使用一般的 **Sign in** 按鈕完成登入。

1. 照常在 **Chrome / Edge / Firefox** 中登入該供應商。
2. 對於 ChatGPT，按下 **F12** → **Network**（網路），重新載入頁面，點選任一
   `chatgpt.com` 請求，並複製完整的 **Request Headers → Cookie:** 值。
   其中包含分段的工作階段 Cookie，以及 `__Secure-oai-is`
   等附屬驗證 Cookie。
3. 對於 Claude，按下 **F12** → **Network**，重新載入 `https://claude.ai/new#settings/usage`，
   點選任一 `claude.ai` 請求，並複製完整的 **Request Headers → Cookie:**
   值。其中必須包含 `sessionKey`。
4. 在應用程式中，開啟「設定」內對應的供應商分頁，點選 **Paste cookie**，貼上標頭內容後儲存。

## 日常使用

- **Windows / Linux：** 拖曳浮動小工具即可移動，並使用
  右下角的握把調整大小。可將其收合為精簡的膠囊，或隱藏到
  系統匣。在小工具或系統匣圖示上按右鍵可開啟完整選單。在
  沒有系統匣的桌面環境中，請改在小工具上按右鍵。
- **macOS：** 選單列項目會顯示每個已啟用
  供應商或帳號的最高用量。點擊即可開啟彈出視窗。
- 「設定」可控制供應商、帳號、顏色、視窗行為、介面縮放、
  重新整理時機與登入時自動啟動。
- 當用量有變動時，每 5 分鐘自動重新整理一次，之後預設會逐步退避，
  最長間隔為 60 分鐘。
- 在 Windows 上，重置提醒會使用通知中心的原生通知；
  點擊通知會在瀏覽器中開啟原始貼文，即使 AI Gauge
  已結束也一樣。同時到達的提醒會同時顯示。若原生
  通知失敗，或在非 Windows 系統上，且有可用的 Qt 系統匣時，
  會改用系統匣氣泡通知。氣泡通知之間至少間隔 8 秒；點擊
  氣泡會開啟最後一則氣泡的貼文。
  macOS 選單列模式，以及沒有系統匣的 Linux 上，不會顯示
  重置通知。重置磚塊仍會在 macOS 彈出視窗與
  無系統匣的 Linux 浮動小工具中更新。
  若 Windows 中已關閉氣泡提示，則不會顯示
  備援氣泡通知。
  AI Gauge 會在
  `HKCU\Software\Classes\AppUserModelId\AloeDesk.AIGauge` 下登錄其
  通知名稱與內建圖示（`DisplayName` =
  `AI Gauge`，`IconUri` = 內建圖示的路徑）；解除安裝後，您可以刪除此機碼。
- 重新整理發生錯誤時，磚塊會顯示簡短的原因；保留的數值會標示為
  `<cause> · stale`（例如 `offline · stale` 或 `timeout · stale`），
  而沒有保留數值的錯誤則顯示 `error · <cause>`。

## 建置獨立執行檔

對大多數使用者而言，[預先建置的下載檔](#下載)較為方便 — 本節適用於在本機建置，或負責發行版本的維護者。建置機器需要 Python 3.11 以上版本，以及已執行過 `pip install -e .[dev]` 的 `.venv`。Windows 建置另外需要 PowerShell 7（`pwsh`）。產出的執行檔在目標機器上**不**需要 Python 或 PowerShell。

| 作業系統 | 指令             | 輸出                         |
| ------- | ---------------- | ---------------------------- |
| Windows | `pwsh -File .\build.ps1` | `dist/ai-gauge/ai-gauge.exe` |
| macOS   | `./build.sh`     | `dist/ai-gauge.app`          |
| Linux   | `./build.sh`     | `dist/ai-gauge/ai-gauge`     |

符合 `v*` 的標籤提交會觸發[發行工作流程](.github/workflows/release.yml)，為三個平台建置並準備附有 SHA256 檔案的 GitHub Release 草稿。另有由維護者手動觸發的測試建置，只會上傳產出檔而不建立發行版本。維護者會在發布前檢查草稿中的產出檔，以及隔離環境下的 GUI／MCP 冒煙測試結果；請參閱 [RELEASING.md](RELEASING.md)。CI 不會驗證實際的供應商帳號。

由於內含 Chromium 執行環境，套件大小約 150–200 MB。使用者資料仍存放於套件之外，位於各作業系統的應用程式資料目錄。

若要建置單一檔案的執行檔（首次啟動較慢），請加上 `-OneFile`（PowerShell）或 `--onefile`（bash）。在 macOS 上，建議使用 `.app` 套件，而非單一檔案形式。

**在有簽章驗證機制的作業系統上首次啟動時的警告** - 發行的產出檔未經簽章：

- **Windows：** SmartScreen -> 「其他資訊」 -> 「仍要執行」。Windows 建置包含產品／版本中繼資料，但未簽章且普及度低的執行檔，仍可能觸發 SmartScreen 或 Microsoft Defender 的信譽警告。
- **macOS：** Gatekeeper 會在首次啟動時攔截。第一次請在 `.app` 上按右鍵 → 打開，或執行一次 `xattr -dr com.apple.quarantine ai-gauge.app`。
- **Linux：** 沒有簽章驗證機制；只要確認 `ai-gauge` 具有執行權限即可。

維護者的發行步驟請參閱 [RELEASING.md](RELEASING.md)。

## 測試

測試需要開發用的額外套件（dev extras），而上述從原始碼執行的安裝步驟並未包含它們：

```powershell
.\.venv\Scripts\python.exe -m pip install -e .[dev]     # Windows
./.venv/bin/python -m pip install -e '.[dev]'           # macOS / Linux
```

```powershell
.\.venv\Scripts\python.exe -m pytest    # Windows
./.venv/bin/python -m pytest            # macOS / Linux
```

自動化測試涵蓋供應商資料解析、組態設定、使用者介面行為、
本機用量追蹤、MCP 防護機制、憑證儲存，以及平台
整合。實際的 Claude 與 Codex 瀏覽器工作階段則以人工方式驗證。

## MCP 用量防護

AI Gauge 內含選用的本機 stdio MCP 伺服器，讓工具可以檢視
已去識別化的用量資料，並以協作方式暫停高成本的工作。請在
**設定 → MCP** 中啟用，設定選用的暫停百分比，並將每個 MCP
用戶端綁定到其帳號：

```text
ai-gauge-mcp --account-id codex-work
```

從原始碼安裝時，還需要執行 `pip install -e '.[mcp]'`。有關用戶端操作說明、
已封裝輔助程式的路徑、macOS 隔離（quarantine）處理方式與防護機制的安全性模型，請參閱
[docs/mcp.md](docs/mcp.md)。

## 參與貢獻

歡迎提交錯誤回報、供應商版面修正與 PR。分支專屬的問題請至
[DraftingDreamer issue 追蹤頁面](https://github.com/DraftingDreamer/ai-gauge/issues)提出。
環境設定、測試指令與應使用的 issue 範本，請參閱 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 注意事項／限制

- 重置公告磚塊沒有百分比，且不會出現在 macOS
  選單列摘要中。
- Antigravity 用量、重置磚塊與原生通知僅在
  Windows 11 上測試過；macOS 與 Linux 尚未測試。
- **為什麼「Sign in」會開啟另一個 Chrome 系列視窗？** Google 會封鎖內嵌 user-agent 中的 OAuth，而 Chrome 的應用程式繫結加密（App-Bound Encryption）又使 AI Gauge 無法讀取您日常使用的瀏覽器設定檔。因此 AI Gauge 會開啟一個全新的暫時性瀏覽器設定檔，透過 Chrome 的本機回送偵錯介面僅接收所選供應商的 Cookie，將其匯入應用程式，然後刪除該暫時性設定檔。
- **Claude／Codex 的頁面版面可能會改變。** 若某個以瀏覽器為基礎的供應商磚塊在上游 UI 更新後顯示「error」，可能需要調整 `src/aigauge/providers/` 下的頁面擷取 JS — 應用程式的其餘部分仍可正常運作。
- **遠端桌面與沒有 GPU 的工作階段需要注意一點。** 這個儀表本身是純 Qt Widgets，可在任何環境執行，包括透過 RDP/XRDP，以及沒有 GPU 的機器。Claude 與 Codex 是透過驅動內嵌的 Chromium 來讀取的，這需要 OpenGL 環境；若工作階段既不提供 GLX 也不提供 EGL，就無法提供此環境。在這種情況下，這些磚塊會回報需要瀏覽器，而 OpenCode Go、GitHub Copilot 與 OpenRouter 使用 API 憑證，可正常運作。大多數 Linux 桌面環境會透過 Mesa 提供軟體 GL，因此這只會發生在單純的 X 伺服器與部分遠端工作階段上。若 AI Gauge 誤判您的工作階段，請設定 `AIGAUGE_FORCE_WEBENGINE=1` 以略過檢查。
- Copilot REST 端點回傳的是帳單用量的_當前日曆月_資料。小工具追蹤的是已消耗的 AI 點數總額相對於內含額度的使用情形；淨數量／金額僅為需付費的超額部分。重置時間以下個月 1 日計算。GitHub 目前並未提供可靠的個人方案額度欄位，因此「設定」使用方案下拉選單，並提供「自訂」作為備援。年繳／以請求次數計費的帳號，則以舊版 premium request 機制作為備援處理。
- **Copilot 用量會有延遲。** Copilot REST 端點的更新速度明顯比 Claude 或 Codex 慢 — 點數統計可能需要數小時才會反映最近的活動。小工具顯示的是 GitHub 回傳的最新數值；請將 Copilot 磚塊視為落後指標，而非即時資料。
- **Copilot AI 點數。** GitHub 已將 Copilot 從依請求次數計算的額度，改為以 token 為基礎的 AI 點數。付費方案仍包含程式碼補全與下一步編輯建議，而 Chat、CLI、雲端代理、Spaces、Spark 與第三方程式碼代理則會消耗 AI 點數。應用程式顯示的是 GitHub 回傳的點數用量；若您的帳號由組織計費，請填入計費組織，讓 AI Gauge 讀取該組織的計費點數池。
- **OpenRouter 使用兩種金鑰類型。** 推論金鑰用於取得 `/key` 的花費資料。管理金鑰則是取得 `/credits` 帳戶餘額與 `/activity` 模型歷史所必需。沒有管理金鑰時，AI Gauge 仍會顯示金鑰層級的花費，但無法顯示餘額或模型活動。
- **OpenRouter 的時間區間以 UTC 為準。** 今日／本月花費取自 OpenRouter 目前的 UTC 日與月欄位。模型活動取自 OpenRouter 預設的 `/activity` 歷史區間：最近 30 個已完成的 UTC 日，不含當前的 UTC 日。
