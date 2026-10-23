param(
    [ValidateSet('serve','run','postprocess','evaluate','query')][string]$Action = 'serve',
    [string]$Source,
    [string]$RunDirectory,
    [ValidateSet('direct','dense','auto')][string]$Contract = 'direct',
    [int]$Port = 8772,
    [string]$Question,
    [switch]$Answer,
    [switch]$PromptJson,
    [switch]$SkipGleaning
)
$ErrorActionPreference = 'Stop'
$ProjectDirectory = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$ProjectPython = Join-Path $ProjectDirectory '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $ProjectPython)) { throw 'The project Python environment is missing. See this sandbox README.' }
$TaskArguments = @((Join-Path $PSScriptRoot 'run_v2.py'), $Action)
if ($Action -eq 'run') {
    if (-not $Source) { throw 'Provide -Source with a full saved DoclingDocument JSON.' }
    $TaskArguments += @('--source', (Resolve-Path -LiteralPath $Source).Path, '--contract', $Contract)
    if ($PromptJson) { $TaskArguments += '--prompt-json' }
    if ($SkipGleaning) { $TaskArguments += '--skip-gleaning' }
} else {
    if ($RunDirectory) { $TaskArguments += @('--run', (Resolve-Path -LiteralPath $RunDirectory).Path) }
    if ($Action -eq 'serve') { $TaskArguments += @('--port', "$Port") }
    if ($Action -eq 'query') {
        if (-not $Question) { throw 'Provide -Question.' }
        $TaskArguments += $Question
        if ($Answer) { $TaskArguments += '--answer' }
    }
}
& $ProjectPython @TaskArguments
exit $LASTEXITCODE
