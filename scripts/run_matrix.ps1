# Runs the business-matrix audit against the isolated scratch DB.
# Usage: powershell -File scripts/run_matrix.ps1 [-Edge] [-Ideas "POLL,KITCHEN"] [-Out <dir>]
param(
  [switch]$Edge,
  [string]$Ideas = "",
  [string]$Out = "",
  [int]$Questions = 3
)
$ErrorActionPreference = "Continue"
$repo = "e:\BebshaX"
$pw = (Select-String -Path "$repo\docker-compose.yml" -Pattern 'POSTGRES_PASSWORD:\s*(\S+)').Matches[0].Groups[1].Value
$env:BEBSHAX_DATABASE_URL = "postgresql+asyncpg://bebshax:$pw@localhost:5433/bebshax_matrix"
$env:PYTHONUTF8 = "1"
$env:PYTHONUNBUFFERED = "1"
$args = @("$repo\scripts\business_matrix_audit.py", "--questions", "$Questions")
if ($Edge) { $args += "--edge" }
if ($Ideas) { $args += @("--ideas", $Ideas) }
if ($Out) { $args += @("--out", $Out) }
Set-Location "$repo\apps\backend"
& "$repo\.venv\Scripts\python.exe" @args
exit $LASTEXITCODE
