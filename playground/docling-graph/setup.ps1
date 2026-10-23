param([string]$Python = "3.12", [switch]$Isolated)
$ErrorActionPreference = "Stop"
$SandboxDirectory = $PSScriptRoot
$ProjectDirectory = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$ProjectPython = Join-Path $ProjectDirectory ".venv\Scripts\python.exe"
$SandboxPython = Join-Path $SandboxDirectory ".venv\Scripts\python.exe"

if (-not $Isolated -and (Test-Path -LiteralPath $ProjectPython)) {
    & $ProjectPython -c "from importlib.metadata import version; assert version('docling-graph') == '1.9.1'; version('litellm')" 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Reusing existing project environment. No installation needed."
        exit 0
    }
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "Install uv first, or create a Python 3.12 environment here and install requirements.txt manually."
}
if (-not (Test-Path -LiteralPath $SandboxPython)) {
    uv venv --python $Python (Join-Path $SandboxDirectory ".venv")
    if ($LASTEXITCODE -ne 0) { throw "Environment creation failed." }
}
# CPU wheels avoid requiring a GPU for this remote-LLM playground.
uv pip install --python $SandboxPython --index-url https://download.pytorch.org/whl/cpu torch==2.14.1+cpu torchvision==0.29.1+cpu
if ($LASTEXITCODE -ne 0) { throw "CPU runtime installation failed." }
uv pip install --python $SandboxPython -r (Join-Path $SandboxDirectory "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "Docling Graph installation failed." }
Write-Host "Sandbox ready: $SandboxDirectory"
