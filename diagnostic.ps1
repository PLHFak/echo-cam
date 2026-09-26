# Diagnostic de la machine pour "Jouer avec le temps".
# Ne modifie rien : lit seulement des informations et les ecrit dans diagnostic.txt
$out = Join-Path $PSScriptRoot "diagnostic.txt"
$r = @()
function Add($titre, $valeur) { $script:r += "== $titre =="; $script:r += ($valeur | Out-String).Trim(); $script:r += "" }

$os = Get-CimInstance Win32_OperatingSystem
Add "Windows" "$($os.Caption) $($os.Version) ($($os.OSArchitecture))"
Add "Processeur" ((Get-CimInstance Win32_Processor).Name)
Add "Memoire vive" ("{0:N1} Go" -f ($os.TotalVisibleMemorySize / 1MB))
Add "Carte(s) graphique(s)" (Get-CimInstance Win32_VideoController | ForEach-Object { "$($_.Name)  (pilote $($_.DriverVersion))" })
Add "Camera(s)" (Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | Where-Object { $_.Class -in "Camera","Image" } | ForEach-Object { "$($_.FriendlyName)  [$($_.Status)]" })
Add "Ecran(s)" (Get-CimInstance Win32_VideoController | ForEach-Object { "$($_.CurrentHorizontalResolution) x $($_.CurrentVerticalResolution)" })
Add "Espace libre sur C:" ("{0:N1} Go" -f ((Get-PSDrive C).Free / 1GB))

$py = @()
if (Get-Command py -ErrorAction SilentlyContinue) { $py += (py -0p 2>&1) } else { $py += "lanceur 'py' : absent" }
if (Get-Command python -ErrorAction SilentlyContinue) { $py += "python : " + (python --version 2>&1) + "  -> " + (Get-Command python).Source } else { $py += "python : absent" }
Add "Python installe(s)" $py

$venv = Join-Path $PSScriptRoot "venv\Scripts\python.exe"
if (Test-Path $venv) { Add "Installation du programme" ((& $venv -m pip list 2>&1) | Select-String "mediapipe|opencv|numpy") }
else { Add "Installation du programme" "pas encore faite (lancer.bat jamais execute)" }

$r | Set-Content -Path $out -Encoding UTF8
notepad $out
