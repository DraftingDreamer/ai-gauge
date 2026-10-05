#requires -version 7
<#
Build a standalone Windows .exe using PyInstaller.

Usage:
    .\build.ps1            # one-folder build (recommended)
    .\build.ps1 -OneFile   # single-file build (slower startup)
#>
param(
    [switch]$OneFile
)

$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Error "Virtualenv not found at .venv. Run: py -m venv .venv; .venv\Scripts\pip install -e .[dev]"
}

& $venvPython -m pip install --quiet pyinstaller
if ($LASTEXITCODE -ne 0) { Write-Error "Could not install/verify PyInstaller." }

$versionInfo = Join-Path $PSScriptRoot "build\pyinstaller-version-info.txt"
& $venvPython (Join-Path $PSScriptRoot "tools\write_pyinstaller_version_info.py") $versionInfo
if ($LASTEXITCODE -ne 0) { Write-Error "Could not generate executable version metadata." }
$appIcon = Join-Path $PSScriptRoot "src\aigauge\assets\aigaugeicon.ico"

if ($OneFile) {
    $targetExe = Join-Path $PSScriptRoot "dist\ai-gauge.exe"
    if (Test-Path $targetExe) {
        try {
            Remove-Item -LiteralPath $targetExe -Force -ErrorAction Stop
        } catch {
            Write-Error "Cannot replace dist\ai-gauge.exe. Close any running ai-gauge.exe process, then build again."
        }
    }
}

$args = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--windowed",
    "--noupx",
    "--name", "ai-gauge",
    "--version-file", $versionInfo,
    "--icon", $appIcon,
    "--paths", "src",
    "--collect-data", "aigauge",
    "--collect-all", "PyQt6.QtWebEngineWidgets",
    "--collect-all", "PyQt6.QtWebEngineCore",
    "pyinstaller_entry.py"
)
if ($OneFile) { $args += "--onefile" }

function Get-ProcessPathState {
    @(
        [Environment]::GetEnvironmentVariables('Process').GetEnumerator() |
            Where-Object { $_.Key -ieq 'PATH' } |
            Sort-Object { [string]$_.Key } |
            ForEach-Object { "$($_.Key)=$($_.Value)" }
    )
}

function Invoke-PyInstaller([string[]]$Arguments) {
    $parentPathState = @(Get-ProcessPathState)
    $process = $null
    try {
        # PyInstaller resolves native DLLs through PATH. Keep inherited tools
        # such as Poppler out of that search so their ICU DLLs cannot shadow
        # the Windows system ICU required by Qt6Core.
        $basePython = (& $venvPython -c "import sys; print(sys.base_prefix)").Trim()
        if ($LASTEXITCODE -ne 0 -or -not $basePython) {
            Write-Error "Could not determine the base Python installation for a clean build PATH."
        }
        $systemRoot = $env:SystemRoot
        if (-not $systemRoot) { $systemRoot = [Environment]::GetFolderPath('Windows') }
        $buildPath = @(
            (Join-Path $projectRoot ".venv\Scripts"),
            $basePython,
            (Join-Path $basePython "Scripts"),
            (Join-Path $systemRoot "System32"),
            $systemRoot
        ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -Unique

        # The Codex Windows runner can expose both Path and PATH in the same
        # process environment. Updating $env:PATH changes only one entry, and
        # CreateProcess may pass the other one to Python. Build a fresh child
        # environment so PyInstaller receives exactly one controlled PATH.
        $startInfo = [Diagnostics.ProcessStartInfo]::new()
        $startInfo.FileName = $venvPython
        $startInfo.WorkingDirectory = $projectRoot
        $startInfo.UseShellExecute = $false
        $startInfo.CreateNoWindow = $true
        $startInfo.RedirectStandardOutput = $true
        $startInfo.RedirectStandardError = $true
        foreach ($argument in $Arguments) {
            [void]$startInfo.ArgumentList.Add($argument)
        }
        foreach ($pathKey in @($startInfo.Environment.Keys | Where-Object { $_ -ieq 'PATH' })) {
            [void]$startInfo.Environment.Remove($pathKey)
        }
        $startInfo.Environment['PATH'] = $buildPath -join ';'

        $childPathKeys = @($startInfo.Environment.Keys | Where-Object { $_ -ieq 'PATH' })
        if ($childPathKeys.Count -ne 1 -or $startInfo.Environment[$childPathKeys[0]] -cne ($buildPath -join ';')) {
            Write-Error "Could not create a clean PyInstaller child environment."
        }

        $process = [Diagnostics.Process]::Start($startInfo)
        if (-not $process) {
            Write-Error "Could not start PyInstaller."
        }
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        $process.WaitForExit()
        $childStdout = $stdoutTask.GetAwaiter().GetResult()
        $childStderr = $stderrTask.GetAwaiter().GetResult()
        if ($childStdout) { [Console]::Out.Write($childStdout) }
        if ($childStderr) { [Console]::Error.Write($childStderr) }
        if ($process.ExitCode -ne 0) {
            Write-Error "PyInstaller build failed with exit code $($process.ExitCode). If dist\ai-gauge\ai-gauge.exe is locked, close the running app and try again."
        }
    } finally {
        if ($process) { $process.Dispose() }
        $currentPathState = @(Get-ProcessPathState)
        if (Compare-Object -ReferenceObject $parentPathState -DifferenceObject $currentPathState -CaseSensitive) {
            Write-Error "The parent PATH environment changed during the PyInstaller build."
        }
    }
}

Invoke-PyInstaller $args

# The helper is an unsigned console binary that MCP clients launch headlessly,
# so a Defender/SmartScreen block is silent. Give it the same product/version
# resource the GUI carries rather than shipping metadata-less bytes.
$mcpVersionInfo = Join-Path $PSScriptRoot "build\pyinstaller-version-info-mcp.txt"
& $venvPython (Join-Path $PSScriptRoot "tools\write_pyinstaller_version_info.py") $mcpVersionInfo "ai-gauge-mcp"
if ($LASTEXITCODE -ne 0) { Write-Error "Could not generate MCP helper version metadata." }

# mcp pulls in httpx, whose optional CLI path reaches pygments, whose img
# formatter imports Pillow — ~13 MB of image codecs in a stdio JSON-RPC server
# that never renders anything. pygments is present because the build venv
# installs .[dev] (pytest needs it), so it is not a declared runtime dependency
# of anything the helper actually calls. A one-file payload is already
# compressed, so it does not shrink again inside the release archive; dropping
# these here is a straight ~8.6 MB off every platform's download.
$mcpArgs = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--console",
    "--onefile",
    "--noupx",
    "--name", "ai-gauge-mcp",
    "--version-file", $mcpVersionInfo,
    "--exclude-module", "PIL",
    "--exclude-module", "pygments",
    "--paths", "src",
    "pyinstaller_mcp_entry.py"
)
try {
    Invoke-PyInstaller $mcpArgs
} catch {
    Write-Error "MCP helper build failed. $($_.Exception.Message)"
}
if (-not $OneFile) {
    $mcpSource = Join-Path $PSScriptRoot "dist\ai-gauge-mcp.exe"
    $mcpTarget = Join-Path $PSScriptRoot "dist\ai-gauge\ai-gauge-mcp.exe"
    try {
        Move-Item -LiteralPath $mcpSource -Destination $mcpTarget -Force -ErrorAction Stop
    } catch {
        Write-Error "Cannot place dist\ai-gauge\ai-gauge-mcp.exe. Close any MCP client using the helper, then build again. ($_)"
    }
}

# release.yml smoke-tests and packages the helper at a fixed path. Fail here,
# with the path named, rather than partway through a tag release.
$expectedMcp = if ($OneFile) {
    Join-Path $PSScriptRoot "dist\ai-gauge-mcp.exe"
} else {
    Join-Path $PSScriptRoot "dist\ai-gauge\ai-gauge-mcp.exe"
}
if (-not (Test-Path -LiteralPath $expectedMcp)) {
    Write-Error "MCP helper missing at expected release path: $expectedMcp"
}

# --collect-all on the WebEngine modules also drags in Chromium's debug
# resource packs, the DevTools front-end, and every Qt translation — ~140 MB
# the app never loads. Strip them before the folder is archived (issue #7).
# One-file builds are already packed by this point, so there is nothing to do.
if (-not $OneFile) {
    Write-Host ""
    Write-Host "Pruning unused Qt/Chromium payload..."
    & $venvPython (Join-Path $PSScriptRoot "tools\prune_bundle.py") (Join-Path $PSScriptRoot "dist\ai-gauge")
    if ($LASTEXITCODE -ne 0) { Write-Error "Bundle prune failed." }
}

Write-Host ""
Write-Host "Build complete." -ForegroundColor Green
if ($OneFile) {
    Write-Host "Binary: dist\ai-gauge.exe"
    Write-Host "MCP helper: dist\ai-gauge-mcp.exe"
} else {
    Write-Host "Folder: dist\ai-gauge\  (run ai-gauge.exe inside)"
    Write-Host "MCP helper: dist\ai-gauge\ai-gauge-mcp.exe"
}
