$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $RepoRoot

$env:PYTHONPATH = "$RepoRoot\src;$env:SUMO_HOME\tools"

$RunRoot = Join-Path $RepoRoot "outputs\runs\three_lane_overnight_residual"
$LogDir = Join-Path $RunRoot "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$BestEvalLog = Join-Path $LogDir "best_residual_all_controllers_48.log"
$SelectionSummary = Join-Path $RepoRoot "outputs\runs\three_lane_checkpoint_selection_residual\checkpoint_selection_summary.csv"
$Best = Import-Csv $SelectionSummary |
  Sort-Object @{ Expression = { [double]$_.mean_queue_excess_area }; Ascending = $true } |
  Select-Object -First 1

if (-not $Best) {
  throw "No checkpoint-selection rows found in $SelectionSummary"
}

$BestEvalPreset = Join-Path $RunRoot "three_lane_evaluation_best_residual_48.yaml"
$BestOutputDir = "outputs\runs\three_lane_evaluation_best_residual_48"
if ($Best.candidate -eq "zero_weights") {
  $BestWeights = "outputs\runs\three_lane_checkpoint_selection_residual\missing_zero_weights.json"
} else {
  $BestWeights = $Best.weights_path
}

$BestEvalPresetLines = Get-Content (Join-Path $RepoRoot "configs\three_lane_evaluation_50_incident_residual.yaml") |
  ForEach-Object {
    if ($_ -match "^EVAL_EPISODES_PER_CONTROLLER:") {
      "EVAL_EPISODES_PER_CONTROLLER: 48"
    } else {
      $_
    }
  }
$Utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllLines($BestEvalPreset, [string[]]$BestEvalPresetLines, $Utf8NoBom)

Write-Host "=== Resume: evaluate best residual candidate against all controllers for 48 episodes ==="
Write-Host "Best candidate: $($Best.candidate)"
Write-Host "Best weights: $BestWeights"
python -m its_signal_control.cli evaluate `
  --preset $BestEvalPreset `
  --weights $BestWeights `
  --headless `
  --output-dir $BestOutputDir 2>&1 | Tee-Object -FilePath $BestEvalLog

Write-Host ""
Write-Host "Best all-controller evaluation:"
Write-Host "  outputs\runs\three_lane_evaluation_best_residual_48\eval_summary.csv"
Write-Host "  outputs\runs\three_lane_evaluation_best_residual_48\eval_paired_summary.csv"
Write-Host "Log:"
Write-Host "  $BestEvalLog"
