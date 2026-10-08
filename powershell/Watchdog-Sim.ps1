param([Parameter(Mandatory=$true)][string]$Root)
$ErrorActionPreference = 'Stop'
$resolvedRoot = [System.IO.Path]::GetFullPath($Root)
$tempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
if (-not $resolvedRoot.StartsWith($tempRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'Watchdog root must be inside the operating-system temporary directory.'
}
if (-not (Test-Path -LiteralPath (Join-Path $resolvedRoot '.simulation-only'))) {
    throw 'Simulation marker missing; refusing all process actions.'
}
$lockPath = Join-Path $resolvedRoot 'watchdog.lock'
$lock = $null
try {
    try {
        $lock = [System.IO.File]::Open($lockPath, [System.IO.FileMode]::OpenOrCreate, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
    } catch {
        Write-Output 'RESULT=LOCK_BUSY'
        exit 0
    }

    $serviceStatePath = Join-Path $resolvedRoot 'service-state.json'
    if (Test-Path -LiteralPath $serviceStatePath) {
        $state = Get-Content -LiteralPath $serviceStatePath -Raw | ConvertFrom-Json
        try {
            $null = Get-Process -Id ([int]$state.process_id) -ErrorAction Stop
            Write-Output "RESULT=ALREADY_RUNNING PID=$($state.process_id)"
            exit 0
        } catch {
            # The isolated process has exited; a new launch may be considered below.
        }
    }

    $leasePath = Join-Path $resolvedRoot 'maintenance-lease.json'
    if (Test-Path -LiteralPath $leasePath) {
        $lease = Get-Content -LiteralPath $leasePath -Raw | ConvertFrom-Json
        $now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
        $valid = ($lease.simulation_only -eq $true) -and ($lease.target_service -eq 'simulated-service') -and ($lease.request_source -eq 'local-test') -and ($lease.lease_id -is [string]) -and ($lease.created_at -le $now) -and ($lease.expires_at -gt $lease.created_at) -and (($lease.expires_at - $lease.created_at) -le 3600)
        if ($valid -and $now -lt [long]$lease.expires_at) {
            Write-Output 'RESULT=MAINTENANCE_SUPPRESSED'
            exit 0
        }
        if ($valid -and $now -ge [long]$lease.expires_at) {
            Write-Output 'RESULT=MAINTENANCE_EXPIRED_RECOVERY'
        } elseif (-not $valid) {
            Write-Output 'RESULT=INVALID_LEASE_RECOVERY'
        }
    }

    $serviceScript = Join-Path $PSScriptRoot 'SimulatedService.ps1'
    $shell = Join-Path $PSHOME 'pwsh.exe'
    if (-not (Test-Path -LiteralPath $shell)) { throw 'PowerShell executable not found.' }
    $child = Start-Process -FilePath $shell -ArgumentList @('-NoProfile', '-File', "`"$serviceScript`"", '-Root', "`"$resolvedRoot`"") -PassThru -WindowStyle Hidden
    $record = @{ process_id = $child.Id; state = 'RUNNING'; started_at = [DateTimeOffset]::UtcNow.ToString('O') }
    [System.IO.File]::WriteAllText($serviceStatePath, ($record | ConvertTo-Json -Compress))
    Write-Output "RESULT=STARTED PID=$($child.Id)"
} finally {
    if ($null -ne $lock) { $lock.Dispose() }
}
