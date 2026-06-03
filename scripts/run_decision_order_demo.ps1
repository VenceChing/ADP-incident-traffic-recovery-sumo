param(
    [switch]$Gui,
    [switch]$UseTrainedWeights
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

if (-not $env:SUMO_HOME) {
    throw "SUMO_HOME is not set. Install SUMO and set SUMO_HOME before running the demo."
}

$env:PYTHONPATH = "$RepoRoot\src;$env:SUMO_HOME\tools;$env:PYTHONPATH"
$argsList = @(
    "-m", "its_signal_control.cli", "demo",
    "--preset", "configs\three_lane_demo_decision_order_distance_decay.yaml",
    "--output-dir", "outputs\runs\three_lane_demo_decision_order_distance_decay"
)

if ($UseTrainedWeights) {
    $weightsPath = "outputs\runs\three_lane_training_50_decision_order_distance_decay\adp_agent_weights.json"
    if (-not (Test-Path -LiteralPath $weightsPath)) {
        throw "Trained weights not found: $weightsPath. Run the training preset first or omit -UseTrainedWeights."
    }
    $argsList += @("--weights", $weightsPath)
}

if ($Gui) {
    $argsList += "--gui"
} else {
    $argsList += "--headless"
}

python @argsList
