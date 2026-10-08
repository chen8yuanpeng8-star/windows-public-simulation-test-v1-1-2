# Windows 纯模拟验收包

本包是独立编写的通用模拟测试项目，不包含或验证任何生产服务源码。所有模拟文件、临时 SQLite、日志和 Python 缓存均写到系统临时目录；测试不连接生产服务、不读取生产数据、不含下单能力。

## 安全边界

- Watchdog 和服务只操作带 `.simulation-only` 标记的临时目录及本包启动的模拟子进程。
- Python 测试使用临时目录和临时 SQLite；`run_tests.ps1` 将字节码缓存及证据写到指定临时目录，不在白名单源码目录创建输出文件。
- FastAPI 测试只验证通用 ASGI lifespan 示例；模拟器不是生产 Watchdog、Worker 或服务生命周期的副本。
- 测试全部通过只表示 `ADAPTER_WINDOWS_TEST`；不表示 `REAL_PRODUCTION_CODE_TEST` 或 `PRODUCTION_RUNTIME_VERIFICATION`。
- GitHub workflow 只允许手动 `workflow_dispatch`，使用标准 `windows-2022` runner，20 分钟超时、单并发、`GITHUB_TOKEN` 只读；不配置 Secrets、不使用 Larger Runner、不上传测试产物。

## 环境要求

- Windows Server 2022 或 Windows 11
- Python 3.11.x
- PowerShell 7 或更新版本
- 至少 4 GB 可用内存、1 GB 临时磁盘
- 临时目录可写；只绑定并立即释放一个 loopback 临时端口

## 本地执行（与 GitHub workflow 相同的解释器顺序）

在解压后的包根目录打开 PowerShell 7。以下命令将 venv、证据和缓存放在包目录之外的系统临时目录，并显式将同一 venv 的 `python.exe` 传给测试入口；无需激活 venv：

```powershell
$work = Join-Path $env:TEMP ("public-sim-" + [guid]::NewGuid().ToString('N'))
$venv = Join-Path $work 'venv'
$evidence = Join-Path $work 'evidence'
New-Item -ItemType Directory -Path $work | Out-Null
py -3.11 -m venv $venv
$python = Join-Path $venv 'Scripts\python.exe'
& $python -m pip install --disable-pip-version-check -r .\requirements-lock.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& $python -m pip check
if ($LASTEXITCODE -ne 0) { throw 'pip check failed.' }
pwsh -NoProfile -File .\run_tests.ps1 -PythonPath $python -EvidenceDirectory $evidence
if ($LASTEXITCODE -ne 0) { throw 'Simulation tests failed.' }
```

入口先验证 Windows/Python/PowerShell、内存、临时目录和 loopback 端口；随后按“依赖检查 → 文件清单/哈希 → 安全扫描 → Python 测试 → PowerShell 子进程测试 → 两组独立数量门禁 → 测试后清单/安全复核”运行。Python 至少 17 项且不得有 skip；PowerShell 至少 5 项且不得失败。零测试、缺依赖、收集错误、任何 skip 或测试失败都会返回非零退出码。结果 JSON、日志与缓存仅写入 `$evidence`。

## GitHub Actions

将本包白名单文件复制到一个全新的公共仓库（不要复制任何其他项目或 `.git` 历史）。在 Actions 页面手动触发 `Windows simulation tests`。工作流在 `$RUNNER_TEMP` 创建 venv 与证据目录，安装锁定依赖并运行 `pip check`，然后把同一个 venv 的 `python.exe` 显式传给 `run_tests.ps1`。workflow 本身不会自动触发，也不保存 artifact；测试输出、退出码和摘要由该次 Actions 运行日志及 job summary 提供。

## 结果解释

只有 Python 与 PowerShell 两组数量门禁均通过且 skip/failure/error 为零，才会输出 `WINDOWS_ADAPTER_TESTS=FULL_PASS`。Windows 子进程行为应在 Windows runner/VM 实际运行后再报告；即使通过，也不能声称生产集成或生产运行身份已验证。
