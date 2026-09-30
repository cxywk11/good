$ErrorActionPreference = 'Stop'
$workspace = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $workspace
if (-not $env:TEST_DATABASE_URL) { throw 'Set TEST_DATABASE_URL to an empty, dedicated PostgreSQL test database. Tests run migrations up/down.' }
& '.\.venv\Scripts\python.exe' -m pytest -q
exit $LASTEXITCODE
