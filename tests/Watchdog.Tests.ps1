$ErrorActionPreference = 'Stop'
$watchdog = Join-Path $PSScriptRoot '..\powershell\Watchdog-Sim.ps1'
$shell = Join-Path $PSHOME 'pwsh.exe'
$root = Join-Path ([System.IO.Path]::GetTempPath()) ("public-sim-" + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $root | Out-Null
New-Item -ItemType File -Path (Join-Path $root '.simulation-only') | Out-Null
$pass = 0
$fail = 0
$childIds = [System.Collections.Generic.List[int]]::new()

function Assert-Equal([string]$Expected, [string]$Actual, [string]$Name) {
    if ($Expected -ne $Actual) { throw "$Name expected '$Expected', got '$Actual'" }
    $script:pass++
    Write-Output "PASS $Name"
}
function Invoke-Watchdog {
    & $shell -NoProfile -File $watchdog -Root $root
}
function Stop-SimulatedService {
    $statePath = Join-Path $root 'service-state.json'
    if (-not (Test-Path -LiteralPath $statePath)) { return }
    $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    $pidValue = [int]$state.process_id
    [System.IO.File]::WriteAllText((Join-Path $root 'stop.request'), 'stop')
    $deadline = [DateTimeOffset]::UtcNow.AddSeconds(5)
    while ([DateTimeOffset]::UtcNow -lt $deadline) {
        if ($null -eq (Get-Process -Id $pidValue -ErrorAction SilentlyContinue)) { return }
        Start-Sleep -Milliseconds 100
    }
    throw "Simulated child $pidValue did not stop cooperatively."
}

try {
    $first = (Invoke-Watchdog | Select-Object -Last 1)
    Assert-Equal 'STARTED' (($first -split ' ')[0] -replace '^RESULT=', '') 'first-start'
    $state = Get-Content -LiteralPath (Join-Path $root 'service-state.json') -Raw | ConvertFrom-Json
    $childIds.Add([int]$state.process_id)
    $second = (Invoke-Watchdog | Select-Object -Last 1)
    Assert-Equal 'ALREADY_RUNNING' (($second -split ' ')[0] -replace '^RESULT=', '') 'duplicate-start-suppressed'

    Stop-SimulatedService
    $now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    $lease = @{ simulation_only = $true; lease_id = [Guid]::NewGuid().ToString(); target_service = 'simulated-service'; created_at = $now; expires_at = $now + 600; request_source = 'local-test' }
    [System.IO.File]::WriteAllText((Join-Path $root 'maintenance-lease.json'), ($lease | ConvertTo-Json -Compress))
    $suppressed = (Invoke-Watchdog | Select-Object -Last 1)
    Assert-Equal 'MAINTENANCE_SUPPRESSED' (($suppressed -split ' ')[0] -replace '^RESULT=', '') 'active-maintenance-suppresses-restart'

    $lease.expires_at = $now - 1
    [System.IO.File]::WriteAllText((Join-Path $root 'maintenance-lease.json'), ($lease | ConvertTo-Json -Compress))
    Remove-Item -LiteralPath (Join-Path $root 'stop.request') -ErrorAction SilentlyContinue
    $recovered = (Invoke-Watchdog | Select-Object -Last 1)
    Assert-Equal 'STARTED' (($recovered -split ' ')[0] -replace '^RESULT=', '') 'expired-maintenance-recovers'
    $state = Get-Content -LiteralPath (Join-Path $root 'service-state.json') -Raw | ConvertFrom-Json
    $childIds.Add([int]$state.process_id)
    Stop-SimulatedService

    Remove-Item -LiteralPath (Join-Path $root 'stop.request') -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath (Join-Path $root 'service-state.json') -ErrorAction SilentlyContinue
    $lease.expires_at = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds() - 1
    [System.IO.File]::WriteAllText((Join-Path $root 'maintenance-lease.json'), ($lease | ConvertTo-Json -Compress))
    $logOne = Join-Path $root 'watchdog-one.txt'
    $logTwo = Join-Path $root 'watchdog-two.txt'
    $arguments = @('-NoProfile', '-File', "`"$watchdog`"", '-Root', "`"$root`"")
    $one = Start-Process -FilePath $shell -ArgumentList $arguments -PassThru -RedirectStandardOutput $logOne -NoNewWindow
    $two = Start-Process -FilePath $shell -ArgumentList $arguments -PassThru -RedirectStandardOutput $logTwo -NoNewWindow
    $one.WaitForExit()
    $two.WaitForExit()
    if ($one.ExitCode -ne 0 -or $two.ExitCode -ne 0) { throw 'Concurrent watchdog invocation failed.' }
    $combinedOutput = @(Get-Content -LiteralPath $logOne) + @(Get-Content -LiteralPath $logTwo)
    $startedCount = @($combinedOutput | Where-Object { $_ -match '^RESULT=STARTED ' }).Count
    Assert-Equal '1' ([string]$startedCount) 'concurrent-invocation-starts-one-child'
    $state = Get-Content -LiteralPath (Join-Path $root 'service-state.json') -Raw | ConvertFrom-Json
    $childIds.Add([int]$state.process_id)
    Stop-SimulatedService

    Write-Output "SUMMARY passed=$pass failed=$fail"
} finally {
    foreach ($pidValue in $childIds) {
        if ($null -ne (Get-Process -Id $pidValue -ErrorAction SilentlyContinue)) {
            throw "Simulated child remains alive: $pidValue"
        }
    }
    Remove-Item -LiteralPath $root -Recurse -ErrorAction SilentlyContinue
}
