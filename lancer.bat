@echo off
rem Double-cliquer ce fichier pour lancer le projet ECHO.
rem Installe/complete l'environnement quand requirements.txt a change.
cd /d "%~dp0"

if not exist venv\Scripts\python.exe (
    echo.
    echo === Creation de l'environnement... ===
    py -3.11 -m venv venv 2>nul
    if not exist venv\Scripts\python.exe py -3.12 -m venv venv 2>nul
    if not exist venv\Scripts\python.exe python -m venv venv
    if not exist venv\Scripts\python.exe (
        echo ERREUR : Python 3.11 ou 3.12 est introuvable. Installez Python 3.12 depuis le Microsoft Store.
        pause
        exit /b 1
    )
)

fc /b requirements.txt venv\req_installee.txt >nul 2>&1
if errorlevel 1 (
    echo.
    echo === Installation des dependances - PyTorch CUDA fait ~3 Go, patientez... ===
    echo.
    venv\Scripts\python.exe -m pip install --upgrade pip
    venv\Scripts\python.exe -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo ERREUR pendant l'installation. Faites une capture de cette fenetre.
        pause
        exit /b 1
    )
    copy /y requirements.txt venv\req_installee.txt >nul
)

echo.
venv\Scripts\python.exe -c "import torch; ok=torch.cuda.is_available(); print('CUDA disponible :', ok); print('GPU :', torch.cuda.get_device_name(0) if ok else 'aucun')"
echo.
echo === Lancement ===
venv\Scripts\python.exe main.py
if errorlevel 1 (
    echo.
    echo Le programme s'est arrete sur une erreur. Faites une capture de cette fenetre.
)
pause
