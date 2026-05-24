param(
    [switch]$Gui
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

if (-not $env:SUMO_HOME) {
    throw "SUMO_HOME is not set. Install SUMO and set SUMO_HOME before running reproduction."
}

$env:PYTHONPATH = "$RepoRoot\src;$env:PYTHONPATH"
$argsList = @(
    "-m", "its_signal_control.cli", "evaluate",
    "--preset", "configs/historical_best.yaml",
    "--weights", "models/historical_best/adp_agent_weights.json"
)
if ($Gui) {
    $argsList += "--gui"
} else {
    $argsList += "--headless"
}

python @argsList
