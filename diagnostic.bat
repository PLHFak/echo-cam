@echo off
rem Double-cliquer : analyse la machine et ouvre le resultat dans le Bloc-notes.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0diagnostic.ps1"
