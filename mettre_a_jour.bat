@echo off
rem Double-cliquer : recupere la derniere version du programme depuis GitHub.
rem Conserve l'installation (venv) : pas besoin de tout reinstaller.
cd /d "%~dp0"
echo Telechargement de la derniere version...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$z=Join-Path $env:TEMP 'echo-cam-maj.zip';" ^
  "$d=Join-Path $env:TEMP 'echo-cam-maj';" ^
  "Invoke-WebRequest 'https://github.com/PLHFak/echo-cam/archive/refs/heads/main.zip' -OutFile $z;" ^
  "if (Test-Path $d) { Remove-Item $d -Recurse -Force };" ^
  "Expand-Archive $z -DestinationPath $d;" ^
  "Copy-Item (Join-Path $d 'echo-cam-main\*') -Destination '%~dp0' -Recurse -Force;" ^
  "Remove-Item $z -Force; Remove-Item $d -Recurse -Force"
if errorlevel 1 (
    echo.
    echo ERREUR pendant la mise a jour. Verifiez la connexion internet.
) else (
    echo.
    echo Mise a jour terminee. Double-cliquez sur lancer.bat pour lancer.
)
pause
