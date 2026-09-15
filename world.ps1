param([ValidateSet('start','stop','status','logs','backup','play')][string]$Action = 'status')
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
switch ($Action) {
 'start' { docker compose up -d db redis houdini_login houdini_blizzard dash web }
 'play' { Start-Process -FilePath (Join-Path $PSScriptRoot 'client/node_modules/electron/dist/electron.exe'); return }
 'stop' { docker compose stop }
 'status' { docker compose ps }
 'logs' { docker compose logs --tail 60 houdini_login houdini_blizzard }
 'backup' {
   $backupDir = Join-Path $PSScriptRoot 'backups'
   New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
   $backupName = 'penguins-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.dump'
   docker compose exec -T db pg_dump -U postgres -Fc -f /tmp/penguins.dump postgres
   if ($LASTEXITCODE -ne 0) { throw 'Database backup failed.' }
   docker compose cp db:/tmp/penguins.dump (Join-Path $backupDir $backupName)
   if ($LASTEXITCODE -ne 0) { throw 'Copying backup failed.' }
   Write-Host "Saved backups/$backupName"
 }
}
if ($LASTEXITCODE -ne 0) { throw "Docker command failed: $LASTEXITCODE" }
