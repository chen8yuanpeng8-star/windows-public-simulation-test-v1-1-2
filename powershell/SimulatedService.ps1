param([Parameter(Mandatory=$true)][string]$Root)
$ErrorActionPreference = 'Stop'
$resolvedRoot = [System.IO.Path]::GetFullPath($Root)
$tempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
if (-not $resolvedRoot.StartsWith($tempRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'Service root must be inside the operating-system temporary directory.'
}
if (-not (Test-Path -LiteralPath (Join-Path $resolvedRoot '.simulation-only'))) {
    throw 'Simulation marker missing; refusing to run.'
}
$pidFile = Join-Path $resolvedRoot 'service-state.json'
$heartbeatFile = Join-Path $resolvedRoot 'heartbeat.txt'
$stopFile = Join-Path $resolvedRoot 'stop.request'
[System.IO.File]::WriteAllText($pidFile, (@{ process_id = $PID; state = 'RUNNING' } | ConvertTo-Json -Compress))
try {
    while (-not (Test-Path -LiteralPath $stopFile)) {
        [System.IO.File]::WriteAllText($heartbeatFile, [DateTimeOffset]::UtcNow.ToString('O'))
        Start-Sleep -Milliseconds 200
    }
}
finally {
    [System.IO.File]::WriteAllText((Join-Path $resolvedRoot 'service-exit.json'), (@{ process_id = $PID; state = 'STOPPED'; exited_at = [DateTimeOffset]::UtcNow.ToString('O') } | ConvertTo-Json -Compress))
}
