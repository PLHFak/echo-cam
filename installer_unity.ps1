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
    Get-Process "Unity Hub" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
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
Etape "2/6 Editeur Unity"
# le Hub graphique verrouille son cache : on le ferme avant la ligne de commande
Get-Process "Unity Hub" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep 2
function Editeurs-Installes {
    (Hub @("editors", "-i")) -join "`n"
}
# n'importe quel editeur moderne convient (2022.3 LTS, Unity 6 "6000.x"...) :
# on prend celui deja installe par le Hub, sinon le plus recent propose
$regex = [regex]"(?:6000|20\d\d)\.\d+\.\d+f\d+"
function Choisit([string]$texte) {
    $v = $regex.Matches($texte) | ForEach-Object Value | Select-Object -Unique
    if (-not $v) { return $null }
    ($v | Sort-Object { [version]($_ -replace "f\d+$", "") } | Select-Object -Last 1)
}
$deja = Choisit (Editeurs-Installes)
if ($deja) {
    $version = $deja
    Write-Host "Editeur deja installe : $version"
} else {
    $dispo = Choisit ((Hub @("editors", "-r")) -join "`n")
    if (-not $dispo) { throw "Aucun editeur propose par Unity Hub (editors -r vide)." }
    Write-Host "Telechargement de Unity $dispo (~7 Go, 20 a 40 min)..."
    Hub @("install", "--version", $dispo) | ForEach-Object { Write-Host $_ }
    $version = Choisit (Editeurs-Installes)
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
# Unity est une application fenetree : il faut l'attendre explicitement
# (Start-Process -Wait), sinon le script file avant la fin de la creation.
function Unity-Attend([string[]]$arguments, [string]$log) {
    $p = Start-Process $unity -ArgumentList $arguments -Wait -PassThru `
                        -RedirectStandardOutput "$log.out" -ErrorAction Stop
    return $p.ExitCode
}

Etape "3/6 Projet echo-galerie"
$manifest = Join-Path $projet "Packages\manifest.json"
if ((Test-Path $projet) -and -not (Test-Path $manifest)) {
    Write-Host "Projet incomplet (passage precedent interrompu) : nettoyage..."
    Remove-Item $projet -Recurse -Force -ErrorAction SilentlyContinue
}
if (-not (Test-Path $manifest)) {
    Write-Host "Creation du projet (2 a 5 min, patientez)..."
    $code = Unity-Attend @("-batchmode", "-quit", "-createProject", "`"$projet`"",
                           "-logFile", "`"$ici\unity_creation.log`"") `
                         "$ici\unity_creation.log"
    if ($code -ne 0 -or -not (Test-Path $manifest)) {
        throw "Creation du projet echouee (code $code - voir unity_creation.log)."
    }
}
Write-Host "Projet : $projet"

# --- 4. Fichiers ECHO -------------------------------------------------------
Etape "4/6 Fichiers ECHO"
Copy-Item (Join-Path $ici "unity\Assets\ECHO") (Join-Path $projet "Assets") `
          -Recurse -Force
Write-Host "Scripts copies dans Assets\ECHO."

# --- 5. Paquet Spout (KlakSpout) --------------------------------------------
Etape "5/6 Paquet Spout (KlakSpout)"
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
$code = Unity-Attend @("-projectPath", "`"$projet`"", "-batchmode", "-quit",
                       "-executeMethod", "GalerieBuilder.Construire",
                       "-logFile", "`"$ici\unity_build.log`"") `
                     "$ici\unity_build.log"
if ($code -ne 0) {
    Write-Warning ("Construction automatique echouee (voir unity_build.log) - " +
                   "l'editeur va s'ouvrir : menu ECHO -> Construire la galerie.")
}
Write-Host "Ouverture de l'editeur Unity..."
Start-Process $unity -ArgumentList "-projectPath", "`"$projet`""
Write-Host ""
Write-Host "TERMINE. Dans Unity : ouvrir la scene Assets/ECHO/Galerie si besoin," `
           "puis bouton Play. Cote ECHO : lancer.bat + touche V." -ForegroundColor Green
