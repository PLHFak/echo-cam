@echo off
rem Double-cliquer ce fichier pour lancer "Jouer avec le temps".
rem La premiere fois, il installe tout (quelques minutes). Ensuite, il lance directement.
cd /d "%~dp0"

if not exist venv\installe.txt (
    echo.
    echo === Premiere installation, patientez quelques minutes... ===
    echo.
    if exist venv rmdir /s /q venv
    py -3.12 -m venv venv 2>nul
    if not exist venv\Scripts\python.exe python -m venv venv
    if not exist venv\Scripts\python.exe (
        echo.
        echo ERREUR : Python 3.11 ou 3.12 est introuvable. Installez Python 3.12 depuis le Microsoft Store.
        pause
        exit /b 1
    )
    venv\Scripts\python.exe -m pip install --upgrade pip
    venv\Scripts\python.exe -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo ERREUR pendant l'installation. Faites une capture de cette fenetre.
        pause
        exit /b 1
    )
    echo ok> venv\installe.txt
)

echo.
echo === Lancement. Touche C = calibrer a 2 m, touche Q = quitter ===
echo.
venv\Scripts\python.exe main.py
if errorlevel 1 (
    echo.
    echo Le programme s'est arrete sur une erreur. Faites une capture de cette fenetre.
)
pause
