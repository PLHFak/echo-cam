@echo off
rem Double-cliquer pour voir ce que la camera sait faire (resolutions,
rem cadences reelles) et ouvrir son panneau de reglages constructeur.
cd /d "%~dp0"

if not exist venv\Scripts\python.exe (
    echo Lancez d'abord lancer.bat une fois pour installer l'environnement.
    pause
    exit /b 1
)

venv\Scripts\python.exe camera_controle.py
pause
