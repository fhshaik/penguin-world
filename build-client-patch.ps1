$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$ffdecVersion = '26.3.0'
$expectedInterfaceHash = '6545EF6025BD8E16C5B5C75452C52EB823EC3F927FFD95A2FAC8869D9266F16F'
$downloads = Join-Path $PSScriptRoot 'downloads'
$sourceRoot = Join-Path $PSScriptRoot 'client-source/interface'
$interfacePath = Join-Path $PSScriptRoot 'vanilla-media/media/play/v2/client/interface.swf'
$originalPath = Join-Path $PSScriptRoot 'client-source/interface-original.swf'
$outputPath = Join-Path $PSScriptRoot 'client-source/interface-patched.swf'
$patchHashPath = Join-Path $PSScriptRoot 'client-source/interface-patched.sha256'
$scriptPath = Join-Path $sourceRoot 'scripts/frame_1/DoAction.as'

New-Item -ItemType Directory -Force -Path $downloads, $sourceRoot | Out-Null

if (-not (Test-Path -LiteralPath $originalPath)) {
  if ((Get-FileHash -LiteralPath $interfacePath -Algorithm SHA256).Hash -ne $expectedInterfaceHash) {
    throw 'interface.swf is not the supported original client. Restore the vanilla media file before patching.'
  }
  Copy-Item -LiteralPath $interfacePath -Destination $originalPath
}
if ((Get-FileHash -LiteralPath $originalPath -Algorithm SHA256).Hash -ne $expectedInterfaceHash) {
  throw 'The saved original interface.swf does not match the supported client.'
}

$ffdecArchive = Join-Path $downloads "ffdec_$ffdecVersion.zip"
$ffdecRoot = Join-Path $downloads "ffdec-$ffdecVersion"
if (-not (Test-Path -LiteralPath (Join-Path $ffdecRoot 'ffdec.jar'))) {
  if (-not (Test-Path -LiteralPath $ffdecArchive)) {
    Invoke-WebRequest -Uri "https://github.com/jindrapetrik/jpexs-decompiler/releases/download/version$ffdecVersion/ffdec_$ffdecVersion.zip" -OutFile $ffdecArchive
  }
  Expand-Archive -LiteralPath $ffdecArchive -DestinationPath $ffdecRoot -Force
}

$jreArchive = Join-Path $downloads 'temurin-jre21.zip'
$jreRoot = Join-Path $downloads 'temurin-jre21'
$java = Get-ChildItem -LiteralPath $jreRoot -Recurse -Filter java.exe -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $java) {
  if (-not (Test-Path -LiteralPath $jreArchive)) {
    Invoke-WebRequest -Uri 'https://api.adoptium.net/v3/binary/latest/21/ga/windows/x64/jre/hotspot/normal/eclipse?project=jdk' -OutFile $jreArchive
  }
  Expand-Archive -LiteralPath $jreArchive -DestinationPath $jreRoot -Force
  $java = Get-ChildItem -LiteralPath $jreRoot -Recurse -Filter java.exe | Select-Object -First 1
}

& $java.FullName -jar (Join-Path $ffdecRoot 'ffdec.jar') -export script $sourceRoot $originalPath
if ($LASTEXITCODE -ne 0) { throw 'JPEXS could not export the interface scripts.' }
python (Join-Path $PSScriptRoot 'client-patches/inject_trade.py') $scriptPath
if ($LASTEXITCODE -ne 0) { throw 'The player-card patch could not be applied.' }
& $java.FullName -jar (Join-Path $ffdecRoot 'ffdec.jar') -replace $originalPath $outputPath '\frame_1\DoAction' $scriptPath
if ($LASTEXITCODE -ne 0) { throw 'JPEXS could not compile the patched interface.' }
Copy-Item -LiteralPath $outputPath -Destination $interfacePath -Force
(Get-FileHash -LiteralPath $interfacePath -Algorithm SHA256).Hash | Set-Content -LiteralPath $patchHashPath
Write-Host 'Installed the in-game player-card Trade button.'
