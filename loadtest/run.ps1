# Raises the rate step by step and prints one line per step.
# Stops once the server falls behind: errors above 5 %, p95 above 5 s, or
# fewer than 90 % of the requested requests actually sent.
#
#   $env:DP_EMAIL = '...'; $env:DP_PASSWORD = '...'
#   ./loadtest/run.ps1 -Scenario me
#   ./loadtest/run.ps1 -Scenario rows-fresh -Rates 5,10,20,40,80 -Duration 20s

param(
    [ValidateSet('login', 'me', 'connectors', 'catalog', 'rows', 'rows-fresh', 'mix')]
    [string]$Scenario = 'me',
    [int[]]$Rates = @(10, 25, 50, 100, 200, 400, 800, 1600),
    [string]$Duration = '30s',
    [string]$BaseUrl = 'http://localhost:8000'
)

$ErrorActionPreference = 'Stop'
if (-not $env:DP_EMAIL -or -not $env:DP_PASSWORD) { throw 'Set DP_EMAIL and DP_PASSWORD first.' }

$results = Join-Path $PSScriptRoot 'results'
New-Item -ItemType Directory -Force $results | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$env:BASE_URL = $BaseUrl
$env:SCENARIO = $Scenario
$env:DURATION = $Duration

$rows = foreach ($rate in $Rates) {
    $out = Join-Path $results "$stamp-$Scenario-$rate.json"
    $env:RATE = $rate
    $env:OUT = $out
    k6 run --quiet --no-color (Join-Path $PSScriptRoot 'step.js') | Out-Null
    if (-not (Test-Path $out)) { Write-Warning "step $rate rps left no summary"; break }
    $r = Get-Content $out -Raw | ConvertFrom-Json
    $row = [pscustomobject]@{
        target   = $r.target_rps
        achieved = [math]::Round($r.achieved_rps, 1)
        'fail %' = [math]::Round($r.failed_pct, 2)
        dropped  = $r.dropped
        'med ms' = [math]::Round($r.med_ms, 1)
        'p95 ms' = [math]::Round($r.p95_ms, 1)
        'p99 ms' = [math]::Round($r.p99_ms, 1)
        'max ms' = [math]::Round($r.max_ms, 1)
        vus      = $r.max_vus
    }
    $row
    Write-Host ($row | Format-Table -HideTableHeaders | Out-String).Trim()
    if ($r.failed_pct -gt 5 -or $r.p95_ms -gt 5000 -or $r.achieved_rps -lt 0.9 * $rate) { break }
}

$rows | Format-Table -AutoSize
