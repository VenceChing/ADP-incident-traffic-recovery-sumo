param(
    [ValidateSet("real_world", "real_world2", "all")]
    [string]$Map = "real_world",
    [ValidateSet("fixed_time", "fixed_time_rr")]
    [string]$Baseline = "fixed_time_rr"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

if (-not $env:SUMO_HOME) {
    throw "SUMO_HOME is not set. Install SUMO and set SUMO_HOME before running GUI demos."
}

$env:PYTHONPATH = "$RepoRoot\src;$env:SUMO_HOME\tools;$env:PYTHONPATH"

function Get-DemoPresets {
    param([string]$MapName)

    if ($MapName -eq "real_world") {
        return @{
            Label = "realmap1"
            AdpPreset = "configs\demo_real_world_adp.yaml"
            BaselinePreset = "configs\demo_real_world_fixed_time.yaml"
        }
    }

    return @{
        Label = "realmap2"
        AdpPreset = "configs\demo_real_world2_adp.yaml"
        BaselinePreset = "configs\demo_real_world2_fixed_time.yaml"
    }
}

$mapNames = if ($Map -eq "all") { @("real_world", "real_world2") } else { @($Map) }
$commands = @()
foreach ($mapName in $mapNames) {
    $presets = Get-DemoPresets -MapName $mapName
    $commands += @(
        @{ Title = "$($presets.Label) ADP"; Preset = $presets.AdpPreset },
        @{ Title = "$($presets.Label) $Baseline"; Preset = $presets.BaselinePreset }
    )
}

foreach ($command in $commands) {
    $argLine = "-NoExit -Command `"`$Host.UI.RawUI.WindowTitle='$($command.Title)'; cd '$RepoRoot'; `$env:PYTHONPATH='$RepoRoot\src;$env:SUMO_HOME\tools'; python -m its_signal_control.cli demo --preset '$($command.Preset)' --gui`""
    Start-Process powershell -ArgumentList $argLine -WindowStyle Normal
    Start-Sleep -Seconds 2
}
