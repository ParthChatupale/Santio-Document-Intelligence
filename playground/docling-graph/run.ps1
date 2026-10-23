param(
    [ValidateSet("inspect", "run", "view")][string]$Action = "inspect",
    [string]$Source,
    [ValidateSet("auto", "direct", "dense")][string]$Contract = "direct",
    [switch]$Isolated
)
$ErrorActionPreference = "Stop"
$ProjectDirectory = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$ProjectPython = Join-Path $ProjectDirectory ".venv\Scripts\python.exe"
$SandboxPython = $ProjectPython
if (-not $Isolated -and (Test-Path -LiteralPath $ProjectPython)) {
    & $ProjectPython -c "from importlib.metadata import version; assert version('docling-graph') == '1.9.1'; version('litellm')" 2>$null
    if ($LASTEXITCODE -ne 0) { $SandboxPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe" }
} else {
    $SandboxPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
}
if (-not (Test-Path -LiteralPath $SandboxPython)) {
    throw "Run this playground's setup.ps1 first."
}
& $SandboxPython -c "from importlib.metadata import version; assert version('docling-graph') == '1.9.1'; version('litellm')" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "Docling Graph is missing from the selected environment. Run setup.ps1 (or setup.ps1 -Isolated for -Isolated runs)."
}
$TaskArguments = @((Join-Path $PSScriptRoot "sandbox.py"), $Action)
if ($Action -ne "view") {
    if (-not $Source) { throw "Provide -Source with a saved DoclingDocument JSON path." }
    $TaskArguments += @("--source", (Resolve-Path -LiteralPath $Source).Path)
}
if ($Action -eq "run") { $TaskArguments += @("--contract", $Contract) }
& $SandboxPython @TaskArguments
exit $LASTEXITCODE
