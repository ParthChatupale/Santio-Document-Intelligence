param([int]$Port = 8765)
$workspacePath = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $workspacePath '.venv\Scripts\python.exe'
& $pythonPath -m pbl_docintel.gui.cli --workspace $workspacePath --port $Port
