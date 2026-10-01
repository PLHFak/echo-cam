@echo off
rem Emetteur Spout de test (fond anime) - lancer ECHO d abord, puis ceci.
cd /d "%~dp0"
venv\Scripts\python.exe emetteur_test.py
pause
