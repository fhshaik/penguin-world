param([string[]]$Paths = @('media/play/v2/client','media/play/v2/content','media/play/v2/games','media/play/web_service','media/avatar','media/play/en','media/play/xml','media/play/content','media/play/start','media/play/swf','media/play/create','media/play/scripts','media/play/images','media/play/css','media/play/upgrade','media/cdn'))
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$revision = 'e8666de19835faf61782358d52a3b41c9226a00a'
$api = 'https://git.solero.me/api/v4/projects/solero%2Fvanilla-media/repository'
New-Item -ItemType Directory -Path downloads -Force | Out-Null
function Get-MediaTree([string]$MediaPath) {
 $archive = Join-Path $PSScriptRoot ('downloads/' + $MediaPath.Replace('/','-') + '.tar.gz')
 $marker = $archive + '.done'
 if (Test-Path $marker) { return }
 Write-Host "Downloading $MediaPath"
 & curl.exe -f -sS -L --connect-timeout 15 --max-time 300 -o $archive "$api/archive.tar.gz?sha=$revision&path=$MediaPath"
 if ($LASTEXITCODE -eq 0) {
  & tar -xzf $archive -C vanilla-media --strip-components=1
  if ($LASTEXITCODE -ne 0) { throw "Extraction failed: $MediaPath" }
  Set-Content -Path $marker -Value $revision
  Write-Host "Ready: $MediaPath"
  return
 }
 Write-Host "Splitting interrupted bundle: $MediaPath"
 $page = 1
 do {
  $entries = Invoke-RestMethod "$api/tree?ref=$revision&path=$MediaPath&per_page=100&page=$page"
  foreach ($entry in $entries) {
   if ($entry.type -eq 'tree') { Get-MediaTree $entry.path }
   else {
    $fileDest = Join-Path (Join-Path $PSScriptRoot 'vanilla-media') $entry.path
    New-Item -ItemType Directory -Path (Split-Path $fileDest) -Force | Out-Null
    $encodedPath = [Uri]::EscapeDataString($entry.path)
    & curl.exe -f -sS -L --connect-timeout 15 --max-time 90 -o $fileDest "$api/files/$encodedPath/raw?ref=$revision"
    if ($LASTEXITCODE -ne 0) { throw "Download failed: $($entry.path)" }
   }
  }
  $page++
 } while ($entries.Count -eq 100)
 Set-Content -Path $marker -Value $revision
}
foreach ($mediaPath in $Paths) { Get-MediaTree $mediaPath }
