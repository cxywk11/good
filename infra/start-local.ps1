$ErrorActionPreference = 'Stop'
$workspace = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $workspace
New-Item -ItemType Directory -Force -Path (Join-Path $workspace '.runtime') | Out-Null
$python = Join-Path $workspace '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Run python -m venv .venv and install dependencies first.' }
& $python infra/init_local.py
& $python -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw 'Migration failed' }
& $python -m jc.bootstrap
if ($LASTEXITCODE -ne 0) { throw 'Bootstrap failed' }
$backend = Start-Process -FilePath $python -ArgumentList @('-m','uvicorn','jc.main:app','--host','127.0.0.1','--port','8000') -WorkingDirectory $workspace -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $workspace '.runtime\api.out.log') -RedirectStandardError (Join-Path $workspace '.runtime\api.err.log')
$node = (Get-Command node.exe).Source
$web = Join-Path $workspace 'apps\web'
$frontend = Start-Process -FilePath $node -ArgumentList @('node_modules/vite/bin/vite.js','--host','127.0.0.1','--port','5173','--strictPort') -WorkingDirectory $web -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $workspace '.runtime\web.out.log') -RedirectStandardError (Join-Path $workspace '.runtime\web.err.log')
@{backend=$backend.Id;frontend=$frontend.Id;started_at=(Get-Date).ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $workspace '.runtime\local-processes.json')
Write-Output 'Local preview: http://127.0.0.1:5173. Administrator credentials: .env. Process IDs: .runtime/local-processes.json.'
