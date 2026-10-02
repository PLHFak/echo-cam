# Installe et prepare la galerie Unity de bout en bout (voir installer_unity.bat).
# Etapes : Unity Hub (winget) -> editeur 2022.3 LTS -> projet echo-galerie ->
# fichiers ECHO -> paquet Spout (KlakSpout) -> construction de la scene ->
# ouverture de l'editeur, pret a jouer.

$ErrorActionPreference = "Stop"
$ici    = Split-Path -Parent $MyInvocation.MyCommand.Path
$projet = Join-Path $HOME "Documents\echo-galerie"

function Etape($t) { Write-Host ""; Write-Host "=== $t ===" -ForegroundColor Cyan }

function Trouve-Hub {
    # 1) chemins habituels (installation machine ou par utilisateur)
    foreach ($p in @("$Env:ProgramFiles\Unity Hub\Unity Hub.exe",
                     "${Env:ProgramFiles(x86)}\Unity Hub\Unity Hub.exe",
                     "$Env:LOCALAPPDATA\Programs\Unity Hub\Unity Hub.exe",
                     "$Env:LOCALAPPDATA\Programs\unityhub\Unity Hub.exe")) {
        if ($p -and (Test-Path $p)) { return $p }
    }
    # 2) registre Windows (ou qu'ait choisi l'installeur)
    foreach ($r in @("HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*",
                     "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*",
                     "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*")) {
        $e = Get-ItemProperty $r -ErrorAction SilentlyContinue |
             Where-Object { $_.DisplayName -like "Unity Hub*" } | Select-Object -First 1
        if ($e -and $e.InstallLocation) {
            $p = Join-Path $e.InstallLocation "Unity Hub.exe"
            if (Test-Path $p) { return $p }
        }
        if ($e -and $e.DisplayIcon) {
            $p = ($e.DisplayIcon -split ",")[0].Trim('"')
            if ($p -like "*Unity Hub.exe" -and (Test-Path $p)) { return $p }
        }
    }
    # 3) raccourcis du menu Demarrer (l'installeur en cree toujours un)
    $shell = New-Object -ComObject WScript.Shell
    foreach ($menu in @("$Env:ProgramData\Microsoft\Windows\Start Menu",
                        "$Env:APPDATA\Microsoft\Windows\Start Menu")) {
        $lnk = Get-ChildItem $menu -Filter "Unity Hub*.lnk" -Recurse `
               -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($lnk) {
            $cible = $shell.CreateShortcut($lnk.FullName).TargetPath
            if ($cible -and (Test-Path $cible)) { return $cible }
        }
    }
    # 4) registre App Paths
    foreach ($r in @("HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\Unity Hub.exe",
                     "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\Unity Hub.exe")) {
        $e = Get-ItemProperty $r -ErrorAction SilentlyContinue
        if ($e -and $e.'(default)' -and (Test-Path $e.'(default)')) { return $e.'(default)' }
    }
    # 5) balayage des dossiers d'installation (tous les profils)
    $racines = @($Env:ProgramFiles, ${Env:ProgramFiles(x86)},
                 "$Env:LOCALAPPDATA\Programs") +
               (Get-ChildItem "C:\Users" -Directory -ErrorAction SilentlyContinue |
                ForEach-Object { Join-Path $_.FullName "AppData\Local\Programs" })
    foreach ($racine in $racines) {
        if (-not $racine -or -not (Test-Path $racine)) { continue }
        $p = Get-ChildItem $racine -Filter "Unity Hub.exe" -Recurse -Depth 3 `
             -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($p) { return $p.FullName }
    }
    return $null
}

function Diagnostic-Hub {
    Write-Host ""
    Write-Host "--- DIAGNOSTIC (a envoyer a Claude) ---" -ForegroundColor Yellow
    winget list --id Unity.UnityHub 2>$null | ForEach-Object { Write-Host $_ }
    foreach ($d in @("$Env:ProgramFiles\Unity Hub",
                     "$Env:LOCALAPPDATA\Programs")) {
        Write-Host "contenu de ${d}:"
        Get-ChildItem $d -ErrorAction SilentlyContinue |
            ForEach-Object { Write-Host "  $($_.Name)" }
    }
    Write-Host "raccourcis Unity trouves :"
    foreach ($menu in @("$Env:ProgramData\Microsoft\Windows\Start Menu",
                        "$Env:APPDATA\Microsoft\Windows\Start Menu")) {
        Get-ChildItem $menu -Filter "*Unity*" -Recurse -ErrorAction SilentlyContinue |
            ForEach-Object { Write-Host "  $($_.FullName)" }
    }
    Write-Host "---------------------------------------" -ForegroundColor Yellow
}

# --- 1. Unity Hub -----------------------------------------------------------
Etape "1/6 Unity Hub"
$hub = Trouve-Hub
if (-not $hub) {
    # winget laisse parfois une installation fantome (fichiers bloques par
    # l'antivirus) : telechargement direct chez Unity + installeur VISIBLE,
    # pour que toute demande (Windows, antivirus) apparaisse a l'ecran.
    Write-Host "Telechargement de l'installeur Unity Hub (unity.com)..."
    $setup = Join-Path $Env:TEMP "UnityHubSetup.exe"
    $ok = $false
    foreach ($url in @(
        "https://public-cdn.cloud.unity3d.com/hub/prod/UnityHubSetup-x64.exe",
        "https://public-cdn.cloud.unity3d.com/hub/prod/UnityHubSetup.exe")) {
        try {
            Invoke-WebRequest $url -OutFile $setup
            if ((Get-Item $setup).Length -gt 10MB) { $ok = $true; break }
        } catch { Write-Host "  (indisponible : $url)" }
    }
    if ($ok) {
        Write-Host ""
        Write-Host ">>> L'installeur Unity Hub va s'ouvrir : cliquez Install / Suivant." `
                   -ForegroundColor Yellow
        Write-Host ">>> Si l'antivirus (AVG) affiche une alerte : AUTORISER." `
                   -ForegroundColor Yellow
        Start-Process $setup -Wait
    } else {
        # filet de secours : page officielle + installation manuelle
        Write-Host ""
        Write-Host ">>> Telechargement automatique impossible : la page officielle" `
                   -ForegroundColor Yellow
        Write-Host ">>> unity.com/download s'ouvre. Cliquez 'Download for Windows'," `
                   -ForegroundColor Yellow
        Write-Host ">>> installez Unity Hub, PUIS revenez ici et pressez Entree." `
                   -ForegroundColor Yellow
        Start-Process "https://unity.com/download"
        Read-Host "Pressez Entree une fois Unity Hub installe"
    }
    for ($i = 0; $i -lt 15 -and -not (Trouve-Hub); $i++) { Start-Sleep 2 }
    $hub = Trouve-Hub
    if (-not $hub) { Diagnostic-Hub; throw "Unity Hub introuvable apres installation." }
    # le Hub se lance souvent tout seul en fin d'installation : on le ferme
    Start-Sleep 3
    Get-Process "Unity Hub" -ErrorAction SilentlyContinue | Stop-Process -Force
}
Write-Host "Unity Hub : $hub"

function Hub([string[]]$arguments) {
    # le Hub ecrit des avertissements sur stderr (cache Chromium...) :
    # on les capture en texte sans en faire des erreurs fatales
    $ancien = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $texte = & $hub -- --headless @arguments 2>&1 | ForEach-Object { "$_" }
    $ErrorActionPreference = $ancien
    $texte
}

# --- 2. Editeur 2022.3 LTS --------------------------------------------------
Etape "2/6 Editeur Unity 2022.3 LTS"
# le Hub graphique verrouille son cache : on le ferme avant la ligne de commande
Get-Process "Unity Hub" -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep 2
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
