from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows build script")


def _ps_literal(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def test_pyinstaller_child_uses_clean_path_and_preserves_parent(tmp_path):
    """Exercise the real build helper without running a full PyInstaller build."""
    project_root = Path(__file__).resolve().parents[1]
    build_script = project_root / "build.ps1"
    python_executable = Path(sys.executable)
    dirty_path = tmp_path / "foreign-poppler-bin"
    dirty_path.mkdir()
    pwsh = shutil.which("pwsh")
    if pwsh is None:
        pytest.skip("PowerShell 7 is required by build.ps1")

    probe = f"""
$buildScript = {_ps_literal(build_script)}
$tokens = $null
$parseErrors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile(
    $buildScript, [ref]$tokens, [ref]$parseErrors
)
if ($parseErrors.Count) {{ throw ($parseErrors -join [Environment]::NewLine) }}
$functionNames = @('Get-ProcessPathState', 'Invoke-PyInstaller')
$functions = $ast.FindAll({{
    param($node)
    $node -is [Management.Automation.Language.FunctionDefinitionAst] -and
        $functionNames -contains $node.Name
}}, $true)
if ($functions.Count -ne 2) {{ throw 'Build helper functions were not found.' }}
foreach ($function in $functions) {{ Invoke-Expression $function.Extent.Text }}

$projectRoot = {_ps_literal(tmp_path)}
$venvPython = {_ps_literal(python_executable)}
$env:PATH = {_ps_literal(str(dirty_path) + ";")} + $env:PATH
$before = @(Get-ProcessPathState)
Invoke-PyInstaller @(
    '-c',
    'import os; print("CHILD_PATH=" + os.environ["PATH"])'
)
$after = @(Get-ProcessPathState)
if (Compare-Object $before $after -CaseSensitive) {{
    throw 'Parent PATH changed during the probe.'
}}
Write-Output 'PARENT_PATH_UNCHANGED=True'
"""

    completed = subprocess.run(
        [pwsh, "-NoProfile", "-Command", probe],
        cwd=project_root,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    child_line = next(
        line for line in completed.stdout.splitlines() if line.startswith("CHILD_PATH=")
    )
    child_path = child_line.removeprefix("CHILD_PATH=")
    assert str(dirty_path).casefold() not in child_path.casefold()
    assert "poppler" not in child_path.casefold()
    assert "libheif" not in child_path.casefold()
    assert str(Path(sys.base_prefix)).casefold() in child_path.casefold()
    assert str(Path(os.environ["SystemRoot"]) / "System32").casefold() in child_path.casefold()
    assert "PARENT_PATH_UNCHANGED=True" in completed.stdout
