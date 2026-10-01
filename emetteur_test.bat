@echo off
rem Emetteur Spout de test (fond anime) - lancer ECHO d abord, puis ceci.
cd /d "%~dp0"
venv\Scripts\python.exe -m pip show SpoutGL >nul 2>&1
if errorlevel 1 (
    echo Installation du module Spout...
    venv\Scripts\python.exe -m pip install SpoutGL
)
venv\Scripts\python.exe emetteur_test.py
pause
