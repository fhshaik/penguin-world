@echo off
cd /d "%~dp0"
start "Penguin World" "%~dp0client\node_modules\electron\dist\electron.exe" "%~dp0client"
