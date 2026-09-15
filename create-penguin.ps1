param([Parameter(Mandatory)][ValidatePattern('^[A-Za-z0-9 ]{4,12}$')][string]$Name)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$secret = Read-Host 'Choose a game password (at least 10 characters)' -AsSecureString
$plain = [System.Net.NetworkCredential]::new('', $secret).Password
try {
  if ($plain.Length -lt 10) { throw 'Use at least 10 characters.' }
  @{ name = $Name; password = $plain } | ConvertTo-Json -Compress | docker compose exec -T houdini_login python local-tools/local-account.py
  if ($LASTEXITCODE -ne 0) { throw 'Account creation failed. Existing accounts were not changed.' }
} finally { $plain = $null; $secret.Dispose() }
