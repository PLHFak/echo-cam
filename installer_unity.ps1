# Installe et prepare la galerie Unity de bout en bout (voir installer_unity.bat).
# Etapes : Unity Hub (winget) -> editeur 2022.3 LTS -> projet echo-galerie ->
# fichiers ECHO -> paquet Spout (KlakSpout) -> construction de la scene ->
# ouverture de l'editeur, pret a jouer.

$ErrorActionPreference = "Stop"
$ici    = Split-Path -Parent $MyInvocation.MyCommand.Path
$projet = Join-Path $HOME "Documents\echo-galerie"

function Etape($t) { Write-Host ""; Write-Host "=== $t ===" -ForegroundColor Cyan }

function Trouve-Hub {
    foreach ($p in @("$Env:ProgramFiles\Unity Hub\Unity Hub.exe",
                     "$Env:LOCALAPPDATA\Programs\Unity Hub\Unity Hub.exe")) {
        if (Test-Path $p) { return $p }
    }
    return $null
}

# --- 1. Unity Hub -----------------------------------------------------------
Etape "1/6 Unity Hub"
$hub = Trouve-Hub
if (-not $hub) {
    Write-Host "Installation de Unity Hub (winget)..."
    winget install --id Unity.UnityHub -e --silent `
        --accept-package-agreements --accept-source-agreements
    for ($i = 0; $i -lt 30 -and -not (Trouve-Hub); $i++) { Start-Sleep 2 }
    $hub = Trouve-Hub
    if (-not $hub) { throw "Unity Hub introuvable apres installation." }
}
Write-Host "Unity Hub : $hub"

function Hub([string[]]$arguments) {
    # le Hub CLI ecrit sur stdout ; on capture tout
    & $hub -- --headless @arguments 2>&1 | ForEach-Object { "$_" }
}

# --- 2. Editeur 2022.3 LTS --------------------------------------------------
Etape "2/6 Editeur Unity 2022.3 LTS"
function Editeurs-Installes {
    (Hub @("editors", "-i")) -join "`n"
}
$regex = [regex]"2022\.3\.\d+f\d+"
$deja  = $regex.Matches((Editeurs-Installes)) | ForEach-Object Value | Select-Object -First 1
if ($deja) {
    $version = $deja
    Write-Host "Deja installe : $version"
} else {
    $dispo = $regex.Matches(((Hub @("editors", "-r")) -join "`n")) |
             ForEach-Object Value | Sort-Object {
                 [int]($_ -replace "2022\.3\.(\d+)f\d+", '$1') } | Select-Object -Last 1
    if (-not $dispo) { throw "Aucune version 2022.3 proposee par Unity Hub." }
    Write-Host "Telechargement de Unity $dispo (~7 Go, 20 a 40 min)..."
    Hub @("install", "--version", $dispo) | ForEach-Object { Write-Host $_ }
    $version = $regex.Matches((Editeurs-Installes)) | ForEach-Object Value | Select-Object -First 1
    if (-not $version) { throw "L'installation de l'editeur a echoue." }
}
$unity = "$Env:ProgramFiles\Unity\Hub\Editor\$version\Editor\Unity.exe"
if (-not (Test-Path $unity)) {
    $ligne = (Editeurs-Installes) -split "`n" | Where-Object { $_ -match [regex]::Escape($version) }
    if ($ligne -match "installed at (.+)$") { $unity = $Matches[1].Trim() }
}
if (-not (Test-Path $unity)) { throw "Unity.exe introuvable pour $version." }
Write-Host "Editeur : $unity"

# --- 3. Projet echo-galerie -------------------------------------------------
Etape "3/6 Projet echo-galerie"
if (-not (Test-Path (Join-Path $projet "Assets"))) {
    Write-Host "Creation du projet (2 a 5 min)..."
    & $unity -batchmode -quit -createProject $projet -logFile "$ici\unity_creation.log"
    if ($LASTEXITCODE -ne 0) { throw "Creation du projet echouee (voir unity_creation.log)." }
} else { Write-Host "Projet deja present : $projet" }

# --- 4. Fichiers ECHO -------------------------------------------------------
Etape "4/6 Fichiers ECHO"
Copy-Item (Join-Path $ici "unity\Assets\ECHO") (Join-Path $projet "Assets") `
          -Recurse -Force
Write-Host "Scripts copies dans Assets\ECHO."

# --- 5. Paquet Spout (KlakSpout) --------------------------------------------
Etape "5/6 Paquet Spout (KlakSpout)"
$manifest = Join-Path $projet "Packages\manifest.json"
$m = Get-Content $manifest -Raw | ConvertFrom-Json
if (-not ($m.PSObject.Properties.Name -contains "scopedRegistries")) {
    $m | Add-Member scopedRegistries @()
}
if (-not ($m.scopedRegistries | Where-Object { $_.name -eq "Keijiro" })) {
    $m.scopedRegistries += [pscustomobject]@{
        name = "Keijiro"; url = "https://registry.npmjs.com"; scopes = @("jp.keijiro") }
}
if (-not ($m.dependencies.PSObject.Properties.Name -contains "jp.keijiro.klak.spout")) {
    $m.dependencies | Add-Member "jp.keijiro.klak.spout" "2.0.3"
}
$m | ConvertTo-Json -Depth 10 | Set-Content $manifest -Encoding UTF8
Write-Host "manifest.json mis a jour."

# --- 6. Construction de la scene, puis ouverture ----------------------------
Etape "6/6 Construction de la galerie"
Write-Host "Import des paquets + construction (3 a 10 min, fenetre invisible)..."
& $unity -projectPath $projet -batchmode -quit `
         -executeMethod GalerieBuilder.Construire -logFile "$ici\unity_build.log"
if ($LASTEXITCODE -ne 0) {
    Write-Warning ("Construction automatique echouee (voir unity_build.log) - " +
                   "l'editeur va s'ouvrir : menu ECHO -> Construire la galerie.")
}
Write-Host "Ouverture de l'editeur Unity..."
Start-Process $unity -ArgumentList "-projectPath", "`"$projet`""
Write-Host ""
Write-Host "TERMINE. Dans Unity : ouvrir la scene Assets/ECHO/Galerie si besoin," `
           "puis bouton Play. Cote ECHO : lancer.bat + touche V." -ForegroundColor Green
