$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$dbDir = Join-Path $repoRoot "Database"
$sqlConfigPath = Join-Path $dbDir "sql_config.json"

if (-not (Test-Path -LiteralPath $sqlConfigPath)) {
    throw "Missing SQL config: $sqlConfigPath"
}

$sqlConfig = Get-Content -LiteralPath $sqlConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $sqlConfig.enabled) {
    throw "SQL is disabled in Database\\sql_config.json"
}

$mysqlCmd = Get-Command mysql.exe -ErrorAction SilentlyContinue
if (-not $mysqlCmd) {
    throw "mysql.exe not found in PATH. Install MySQL client tools or add mysql.exe to PATH."
}

$queries = @"
DELETE FROM finished_jobs;
DELETE FROM archived_jobs_server;
DELETE FROM machine_status_archive;
DELETE FROM active_machine_sessions;
DELETE FROM app_logs;
SELECT 'finished_jobs' AS table_name, COUNT(*) AS row_count FROM finished_jobs
UNION ALL
SELECT 'archived_jobs_server', COUNT(*) FROM archived_jobs_server
UNION ALL
SELECT 'machine_status_archive', COUNT(*) FROM machine_status_archive
UNION ALL
SELECT 'active_machine_sessions', COUNT(*) FROM active_machine_sessions
UNION ALL
SELECT 'app_logs', COUNT(*) FROM app_logs;
"@

$env:MYSQL_PWD = [string]$sqlConfig.password
try {
    & $mysqlCmd.Source `
        --host="$($sqlConfig.host)" `
        --port="$([int]$sqlConfig.port)" `
        --user="$($sqlConfig.user)" `
        --database="$($sqlConfig.database)" `
        --batch `
        --raw `
        --execute=$queries

    if ($LASTEXITCODE -ne 0) {
        throw "mysql.exe exited with code $LASTEXITCODE"
    }
}
finally {
    Remove-Item Env:MYSQL_PWD -ErrorAction SilentlyContinue
}

$jsonResets = @{
    (Join-Path $dbDir "active_machine_sessions.json") = "{}"
    (Join-Path $dbDir "app_logs.json") = "[]"
}

foreach ($path in $jsonResets.Keys) {
    Set-Content -LiteralPath $path -Value $jsonResets[$path] -Encoding UTF8
}

Write-Host ""
Write-Host "Reset complete."
Write-Host "Cleared SQL tables:"
Write-Host "  finished_jobs"
Write-Host "  archived_jobs_server"
Write-Host "  machine_status_archive"
Write-Host "  active_machine_sessions"
Write-Host "  app_logs"
Write-Host ""
Write-Host "Reset local files:"
Write-Host "  Database\\active_machine_sessions.json"
Write-Host "  Database\\app_logs.json"
Write-Host ""
Write-Host "Not touched:"
Write-Host "  user_qr_profiles"
Write-Host "  daily_role_assignments"
Write-Host "  client_settings"
Write-Host "  server settings / API settings / SQL config"
