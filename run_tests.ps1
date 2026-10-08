param(
    [string]$PythonPath = 'python',
    [string]$EvidenceDirectory = (Join-Path ([System.IO.Path]::GetTempPath()) 'public-windows-sim-evidence')
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$originalLocation = Get-Location
$evidence = [System.IO.Path]::GetFullPath($EvidenceDirectory)
$started = [DateTimeOffset]::UtcNow
$pythonExit = -1
$powershellExit = -1
$pythonTests = 0
$pythonPassed = 0
$pythonSkipped = 0
$pythonFailures = 0
$pythonErrors = 0
$powershellPassed = 0
$powershellFailed = 0
$powershellGateExit = -1
$pythonVersion = 'UNKNOWN'
$freeMb = 0
$manifestHash = 'UNKNOWN'
$transcriptStarted = $false
$oldEnvironment = @{
    PYTHONPATH = $env:PYTHONPATH
    PYTHONDONTWRITEBYTECODE = $env:PYTHONDONTWRITEBYTECODE
    PYTHONPYCACHEPREFIX = $env:PYTHONPYCACHEPREFIX
    PYTHONNOUSERSITE = $env:PYTHONNOUSERSITE
}

function Write-Result([string]$Status, [string]$FailureReason) {
    $result = [ordered]@{
        status = $Status
        started_at = $started.ToString('O')
        finished_at = [DateTimeOffset]::UtcNow.ToString('O')
        windows_version = [Environment]::OSVersion.Version.ToString()
        python_version = $pythonVersion
        powershell_version = $PSVersionTable.PSVersion.ToString()
        available_memory_mb = $freeMb
        test_manifest_sha256 = $manifestHash
        python_test_count = $pythonTests
        python_passed = $pythonPassed
        python_skipped = $pythonSkipped
        python_failures = $pythonFailures
        python_errors = $pythonErrors
        powershell_passed = $powershellPassed
        powershell_failed = $powershellFailed
        powershell_gate_exit_code = $powershellGateExit
        python_exit_code = $pythonExit
        powershell_exit_code = $powershellExit
        failure_reason = $FailureReason
    }
    $json = $result | ConvertTo-Json -Depth 5
    $json | Set-Content -LiteralPath (Join-Path $evidence 'run-result.json') -Encoding utf8
    Write-Output $json
    if ($env:GITHUB_STEP_SUMMARY) {
        $summaryBlock = '```json' + [Environment]::NewLine + $json + [Environment]::NewLine + '```' + [Environment]::NewLine
        [System.IO.File]::AppendAllText($env:GITHUB_STEP_SUMMARY, $summaryBlock)
    }
}

try {
    New-Item -ItemType Directory -Force -Path $evidence | Out-Null
    Start-Transcript -Path (Join-Path $evidence 'execution.log') -Force | Out-Null
    $transcriptStarted = $true
    Set-Location -LiteralPath $root

    if ($env:OS -ne 'Windows_NT') { throw 'Windows is required.' }
    if ($PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 or newer is required.' }
    if (Test-Path -LiteralPath $PythonPath -PathType Leaf) {
        $pythonExe = (Resolve-Path -LiteralPath $PythonPath).Path
    } else {
        $pythonCommand = Get-Command -Name $PythonPath -CommandType Application -ErrorAction Stop
        $pythonExe = $pythonCommand.Source
    }
    $pythonVersion = & $pythonExe -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"
    if ($LASTEXITCODE -ne 0 -or $pythonVersion -notmatch '^3\.11\.') { throw "Python 3.11.x required; found $pythonVersion" }

    $os = Get-CimInstance Win32_OperatingSystem
    $freeMb = [math]::Floor($os.FreePhysicalMemory / 1024)
    if ($freeMb -lt 4096) { throw "At least 4096 MB free memory required; found $freeMb MB" }
    $probe = Join-Path $evidence 'write-probe.tmp'
    [System.IO.File]::WriteAllText($probe, 'isolated')
    Remove-Item -LiteralPath $probe
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
    $listener.Start()
    $port = ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port
    $listener.Stop()

    $env:PYTHONPATH = $root
    $env:PYTHONDONTWRITEBYTECODE = '1'
    $env:PYTHONPYCACHEPREFIX = Join-Path $evidence 'pycache'
    $env:PYTHONNOUSERSITE = '1'

    & $pythonExe scripts/verify_manifest.py
    if ($LASTEXITCODE -ne 0) { throw 'Manifest verification failed.' }
    $manifestHash = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $root 'TEST_MANIFEST.json')).Hash.ToLowerInvariant()
    & $pythonExe scripts/security_scan.py
    if ($LASTEXITCODE -ne 0) { throw 'Sensitive-content scan failed.' }
    & $pythonExe -c "import fastapi, sqlite3; print('DEPENDENCIES_OK fastapi=' + fastapi.__version__)"
    if ($LASTEXITCODE -ne 0) { throw 'Locked FastAPI dependency is unavailable in the selected Python environment.' }
    & $pythonExe -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'pip check failed in the selected Python environment.' }

    Write-Output "ENV windows=$([Environment]::OSVersion.Version) python=$pythonVersion powershell=$($PSVersionTable.PSVersion) free_mb=$freeMb loopback_probe_port=$port python_executable=$pythonExe"
    $pythonOutput = & $pythonExe scripts/run_python_tests.py 2>&1
    $pythonExit = $LASTEXITCODE
    $pythonOutput | Tee-Object -FilePath (Join-Path $evidence 'python-tests.log')
    $summaryLine = @($pythonOutput | ForEach-Object { [string]$_ } | Where-Object { $_ -like 'PYTHON_TEST_SUMMARY_JSON=*' } | Select-Object -Last 1)
    if ($summaryLine.Count -ne 1) { throw 'Python test runner did not emit exactly one structured summary.' }
    $pythonSummary = $summaryLine[0].Substring('PYTHON_TEST_SUMMARY_JSON='.Length) | ConvertFrom-Json
    $pythonTests = [int]$pythonSummary.tests_run
    $pythonPassed = [int]$pythonSummary.passed
    $pythonSkipped = [int]$pythonSummary.skipped
    $pythonFailures = [int]$pythonSummary.failures
    $pythonErrors = [int]$pythonSummary.errors
    if ($pythonTests -lt 17) { throw "Python test count below required minimum: $pythonTests < 17" }
    if ($pythonSkipped -gt 0) { throw "Python skips block FULL_PASS: $pythonSkipped" }
    if (($pythonFailures + $pythonErrors) -gt 0 -or -not $pythonSummary.full_pass) { throw 'Python test-count gate failed.' }
    if ($pythonExit -ne 0 -or [int]$pythonSummary.exit_code -ne 0) { throw "Python test suite failed with exit code $pythonExit" }

    $powershellExe = Join-Path $PSHOME 'pwsh.exe'
    $powershellOutput = & $powershellExe -NoProfile -File (Join-Path $root 'tests\Watchdog.Tests.ps1') 2>&1
    $powershellExit = $LASTEXITCODE
    $powershellOutput | Tee-Object -FilePath (Join-Path $evidence 'powershell-tests.log')
    $powershellText = $powershellOutput -join "`n"
    $psMatch = [regex]::Match($powershellText, 'SUMMARY passed=(\d+) failed=(\d+)')
    if (-not $psMatch.Success) { throw 'PowerShell test runner did not emit its structured assertion summary.' }
    $powershellPassed = [int]$psMatch.Groups[1].Value
    $powershellFailed = [int]$psMatch.Groups[2].Value
    $powershellGateOutput = & $pythonExe scripts/check_powershell_counts.py --passed $powershellPassed --failed $powershellFailed --minimum 5 2>&1
    $powershellGateExit = $LASTEXITCODE
    $powershellGateOutput | Tee-Object -FilePath (Join-Path $evidence 'powershell-count-gate.log')
    if ($powershellGateExit -ne 0) { throw 'PowerShell test-count gate failed.' }
    if ($powershellExit -ne 0) { throw "PowerShell simulation failed with exit code $powershellExit" }

    & $pythonExe scripts/verify_manifest.py
    if ($LASTEXITCODE -ne 0) { throw 'Post-test file manifest verification failed; tests may have written into the package directory.' }
    & $pythonExe scripts/security_scan.py
    if ($LASTEXITCODE -ne 0) { throw 'Post-test sensitive-content scan failed.' }
} catch {
    $failure = $_.Exception.Message
    Write-Output "ERROR: $failure"
    if (Test-Path -LiteralPath $evidence) { Write-Result 'FAIL' $failure }
    if ($transcriptStarted) { Stop-Transcript | Out-Null }
    Set-Location -LiteralPath $originalLocation
    foreach ($key in $oldEnvironment.Keys) {
        if ($null -eq $oldEnvironment[$key]) { Remove-Item -Path "Env:$key" -ErrorAction SilentlyContinue }
        else { Set-Item -Path "Env:$key" -Value $oldEnvironment[$key] }
    }
    exit 1
}

Write-Result 'PASS' $null
if ($transcriptStarted) { Stop-Transcript | Out-Null }
Set-Location -LiteralPath $originalLocation
foreach ($key in $oldEnvironment.Keys) {
    if ($null -eq $oldEnvironment[$key]) { Remove-Item -Path "Env:$key" -ErrorAction SilentlyContinue }
    else { Set-Item -Path "Env:$key" -Value $oldEnvironment[$key] }
}
Write-Output 'WINDOWS_ADAPTER_TESTS=FULL_PASS'
