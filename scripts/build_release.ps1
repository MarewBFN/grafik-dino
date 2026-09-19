<#
.SYNOPSIS
    Buduje exe dla wskazanego kanalu wydan (Dino / Enyo / ...) bez ryzyka
    zostawienia zlego kanalu zacommitowanego w release_channel.py.

.DESCRIPTION
    release_channel.py w repo ZAWSZE ma RELEASE_CHANNEL = "dino" - to jest
    kanal domyslny uzywany przez zwykle buildy. Ten skrypt na czas builda
    podmienia te wartosc na wskazany kanal, uruchamia PyInstaller wedlug
    podanego pliku .spec, a na koniec ZAWSZE przywraca plik do stanu z gita,
    nawet jesli build sie wywali.

.PARAMETER Channel
    Kanal wydan do zbudowania, np. "dino" albo "enyo".

.PARAMETER SpecFile
    Plik .spec do przekazania do PyInstallera. Domyslnie
    "Dingo! - narzedzie do grafikow pracy.spec".

.EXAMPLE
    scripts\build_release.ps1 -Channel enyo
#>

param(
    [Parameter(Mandatory = $true)]
    [string]$Channel,

    [string]$SpecFile = "Dingo! - narzędzie do grafików pracy.spec"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$channelFile = Join-Path $repoRoot "release_channel.py"

Push-Location $repoRoot
try {
    $originalContent = Get-Content -Path $channelFile -Raw

    $gitDiff = git diff --name-only -- release_channel.py
    if ($gitDiff) {
        throw "release_channel.py ma juz niezacommitowane zmiany. Zacommituj lub odrzuc je przed buildem, zeby skrypt mogl bezpiecznie przywrocic oryginalna zawartosc."
    }

    Write-Host "==> Buduje kanal: $Channel" -ForegroundColor Cyan

    $newContent = $originalContent -replace 'RELEASE_CHANNEL\s*=\s*"[^"]*"', "RELEASE_CHANNEL = `"$Channel`""
    if ($newContent -eq $originalContent) {
        throw "Nie udalo sie podmienic RELEASE_CHANNEL w release_channel.py - sprawdz format pliku."
    }
    Set-Content -Path $channelFile -Value $newContent -NoNewline -Encoding utf8

    pyinstaller $SpecFile
    $buildExitCode = $LASTEXITCODE

    if ($buildExitCode -eq 0) {
        Write-Host "==> Build zakonczony sukcesem dla kanalu '$Channel'." -ForegroundColor Green
    } else {
        Write-Host "==> Build ZAKONCZONY BLEDEM (kod $buildExitCode) dla kanalu '$Channel'." -ForegroundColor Red
    }
}
finally {
    Write-Host "==> Przywracam release_channel.py do stanu z repo (dino)." -ForegroundColor Cyan
    git checkout -- release_channel.py

    $restored = Get-Content -Path $channelFile -Raw
    if ($restored -notmatch 'RELEASE_CHANNEL\s*=\s*"dino"') {
        Write-Host "!!! UWAGA: release_channel.py NIE zostal poprawnie przywrocony do 'dino'. Sprawdz recznie przed commitem!" -ForegroundColor Red
    }

    Pop-Location
}

if ($buildExitCode -ne 0) {
    exit $buildExitCode
}
