param(
    [ValidateSet("grid_4x4_3lane", "real_world", "real_world2", "real_world2_norm", "all")]
    [string]$Map = "grid_4x4_3lane"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

if (-not $env:SUMO_HOME) {
    throw "SUMO_HOME is not set. Install SUMO and set SUMO_HOME before running GUI demos."
}

$env:PYTHONPATH = "$RepoRoot\src;$env:SUMO_HOME\tools;$env:PYTHONPATH"
$logDir = Join-Path $RepoRoot "outputs\logs\demo_compare"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null

Add-Type -AssemblyName System.Windows.Forms
$workArea = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
$halfWidth = [Math]::Floor($workArea.Width / 2)
$rightWidth = $workArea.Width - $halfWidth
$leftPosition = "$($workArea.X),$($workArea.Y)"
$rightPosition = "$($workArea.X + $halfWidth),$($workArea.Y)"
$leftSize = "$halfWidth,$($workArea.Height)"
$rightSize = "$rightWidth,$($workArea.Height)"

function Get-DemoPresets {
    param([string]$MapName)

    if ($MapName -eq "grid_4x4_3lane") {
        return @{
            Label = "grid_4x4_3lane"
            AdpPreset = "configs\demo_grid_4x4_3lane_adp.yaml"
            BaselinePreset = "configs\demo_grid_4x4_3lane_fixed_time.yaml"
        }
    }

    if ($MapName -eq "real_world") {
        return @{
            Label = "real_world"
            AdpPreset = "configs\demo_real_world_adp.yaml"
            BaselinePreset = "configs\demo_real_world_fixed_time.yaml"
        }
    }

    if ($MapName -eq "real_world2_norm") {
        return @{
            Label = "real_world2_norm"
            AdpPreset = "configs\demo_real_world2_norm_checkerboard_adp.yaml"
            BaselinePreset = "configs\demo_real_world2_norm_fixed_time.yaml"
        }
    }

    return @{
        Label = "real_world2"
        AdpPreset = "configs\demo_real_world2_adp.yaml"
        BaselinePreset = "configs\demo_real_world2_fixed_time.yaml"
    }
}

function Update-RealWorld2NormRoute {
    $scenarioDir = Join-Path $RepoRoot "scenarios\real_world2"
    $targetRoute = Join-Path $scenarioDir "map2_3lane_norm_demo_rate3600.rou.xml"

    Push-Location $scenarioDir
    try {
        & python -c "from its_signal_control import config; config.NETWORK_FILE='map2_3lane_norm.net.xml'; from its_signal_control.utils import generate_routes; generate_routes(3600, 4000, 'map2_3lane_norm_demo_rate3600.rou.xml')"
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to generate $targetRoute"
        }
        Write-Host "Generated route: $targetRoute"
    }
    finally {
        Pop-Location
    }
}

$mapNames = if ($Map -eq "all") { @("grid_4x4_3lane", "real_world", "real_world2") } else { @($Map) }
if ($mapNames -contains "real_world2_norm") {
    Update-RealWorld2NormRoute
}

$commands = @()
foreach ($mapName in $mapNames) {
    $presets = Get-DemoPresets -MapName $mapName
    $commands += @(
        @{
            Title = "$($presets.Label) fixed-time"
            Preset = $presets.BaselinePreset
            WindowSize = $rightSize
            WindowPosition = $rightPosition
        },
        @{
            Title = "$($presets.Label) ADP"
            Preset = $presets.AdpPreset
            WindowSize = $leftSize
            WindowPosition = $leftPosition
        }
    )
}

foreach ($command in $commands) {
    $logName = ($command.Title -replace '[^A-Za-z0-9_-]', '_')
    $stdoutLog = Join-Path $logDir "$logName.stdout.log"
    $stderrLog = Join-Path $logDir "$logName.stderr.log"
    $arguments = @(
        "-u",
        "-m", "its_signal_control.cli",
        "demo",
        "--preset", $command.Preset,
        "--gui",
        "--gui-window-size", $command.WindowSize,
        "--gui-window-pos", $command.WindowPosition
    )
    $process = Start-Process python `
        -ArgumentList $arguments `
        -WorkingDirectory $RepoRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $stdoutLog `
        -RedirectStandardError $stderrLog `
        -PassThru
    Write-Host "Started $($command.Title) controller (PID $($process.Id))"
}

Write-Host "Demo controller logs: $logDir"
