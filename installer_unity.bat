@echo off
rem Installe et prepare la galerie Unity de bout en bout (un seul double-clic).
rem Duree : 30 a 60 min au premier passage (Unity ~7 Go a telecharger).
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer_unity.ps1"
if errorlevel 1 echo ERREUR : faites une capture de cette fenetre pour Claude.
pause
