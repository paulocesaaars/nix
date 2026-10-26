# Instala o binário do Nix (sem Python), grava NIX_HOME, coloca bin no PATH
# e inicia nix init se ainda não houver settings.db.
#
# Uso:
#   irm https://raw.githubusercontent.com/paulocesaaars/nix/main/install.ps1 | iex
#   .\install.ps1 --vault "C:/Obsidian/MeuVault"
#
# Variáveis:
#   NIX_VERSION   tag da release (com ou sem o v inicial). Vazio = última estável.
#   NIX_HOME      pasta da instalação. Vazio = valor já gravado no usuário, ou
#                 %LOCALAPPDATA%\nix.

$ErrorActionPreference = "Stop"
$script:NixSourced = ($MyInvocation.InvocationName -eq ".")

$Repo = "paulocesaaars/nix"
$BaseUrl = "https://github.com/$Repo/releases/download"

function Stop-NixInstall([int]$Code) {
    if ($script:NixSourced) { throw "nix-install exit $Code" }
    exit $Code
}

function Die([string]$Message) {
    [Console]::Error.WriteLine("nix-install: $Message")
    Stop-NixInstall 1
}

if ($args.Count -eq 1 -and $args[0] -in @("-h", "--help")) {
    Write-Host @"
Baixa o binário do Nix para a pasta de instalação, grava NIX_HOME, coloca
{NIX_HOME}\bin no PATH do usuário e, se não houver settings.db, executa nix init.

Argumentos extras vão para nix init, por exemplo:
  .\install.ps1 --vault "C:/Obsidian/MeuVault"

NIX_VERSION escolhe a release (ex.: 1.2.3 ou v1.2.3). Sem isso, vale a última estável.
"@
    Stop-NixInstall 0
}

function Get-NixArch {
    $arch = $env:PROCESSOR_ARCHITECTURE
    if ($env:PROCESSOR_ARCHITEW6432) { $arch = $env:PROCESSOR_ARCHITEW6432 }
    switch ($arch) {
        "AMD64" { return "amd64" }
        "ARM64" {
            Die "windows-arm64 ainda não tem binário publicado. Instale em um Windows amd64."
        }
        default {
            Die "Arquitetura não suportada: $arch. Os binários publicados são windows-amd64, linux-amd64, linux-arm64 e darwin-arm64."
        }
    }
}

function Get-InstallRoot {
    if ($env:NIX_HOME) { return $env:NIX_HOME }
    $stored = [Environment]::GetEnvironmentVariable("NIX_HOME", "User")
    if ($stored) { return $stored }
    if (-not $env:LOCALAPPDATA) {
        Die "LOCALAPPDATA não está definida. Defina NIX_HOME com a pasta da instalação e rode de novo."
    }
    return (Join-Path $env:LOCALAPPDATA "nix")
}

function Add-NixUserPath([string]$Root) {
    $bin = (Join-Path $Root "bin").TrimEnd("\")
    $expand = "%NIX_HOME%\bin"
    [Environment]::SetEnvironmentVariable("NIX_HOME", $Root, "User")
    $current = [Environment]::GetEnvironmentVariable("Path", "User")
    if (-not $current) { $current = "" }
    foreach ($raw in ($current -split ";")) {
        $token = $raw.Trim().Trim('"')
        if (-not $token) { continue }
        $normalized = $token.Replace("/", "\").TrimEnd("\")
        if ($normalized -ieq "%NIX_HOME%\bin") { return }
        $expanded = [Environment]::ExpandEnvironmentVariables($token).TrimEnd("\")
        if ($expanded -ieq $bin) { return }
    }
    $updated = if ($current.Trim()) { $current.TrimEnd(";") + ";" + $expand } else { $expand }
    [Environment]::SetEnvironmentVariable("Path", $updated, "User")
}

$Arch = Get-NixArch
$Tag = $env:NIX_VERSION
$Headers = @{
    "User-Agent" = "nix-install"
    "Accept"     = "application/vnd.github+json"
}
if (-not $Tag) {
    Write-Host "nix-install: resolvendo a última release estável..."
    try {
        $release = Invoke-RestMethod -Headers $Headers -UseBasicParsing "https://api.github.com/repos/$Repo/releases/latest"
    }
    catch {
        Die "Não foi possível consultar a release. Defina NIX_VERSION (ex.: 1.2.3) ou tente de novo. $_"
    }
    $Tag = $release.tag_name
}
if (-not $Tag) { Die "Não achei uma release estável. Publique uma tag vX.Y.Z ou defina NIX_VERSION." }
if ($Tag -notmatch "^v") { $Tag = "v$Tag" }
$Version = $Tag -replace "^v", ""
$Asset = "nix-$Version-windows-$Arch.exe"

$Root = Get-InstallRoot
$BinDir = Join-Path $Root "bin"
$Dest = Join-Path $BinDir "nix.exe"
$Work = Join-Path $env:TEMP ("nix-install-" + [guid]::NewGuid().ToString())
New-Item -ItemType Directory -Path $Work | Out-Null

try {
    Write-Host "nix-install: baixando $Asset ($Tag)..."
    try {
        Invoke-WebRequest -Headers $Headers -UseBasicParsing -Uri "$BaseUrl/$Tag/$Asset" -OutFile (Join-Path $Work $Asset)
        Invoke-WebRequest -Headers $Headers -UseBasicParsing -Uri "$BaseUrl/$Tag/checksums.txt" -OutFile (Join-Path $Work "checksums.txt")
    }
    catch {
        Die "Não baixei $Asset da release $Tag. Confira NIX_VERSION e a conexão, e rode de novo. $_"
    }

    $checksums = Get-Content (Join-Path $Work "checksums.txt")
    $expectedLine = $checksums | Where-Object { $_ -match ([regex]::Escape($Asset) + '$') } | Select-Object -First 1
    if (-not $expectedLine) { Die "checksums.txt da release $Tag não lista $Asset. Rode o instalador de novo quando a release estiver completa." }
    $expected = (($expectedLine -split '\s+', 2)[0]).ToLower()
    $actual = (Get-FileHash -Algorithm SHA256 (Join-Path $Work $Asset)).Hash.ToLower()
    if ($expected -ne $actual) {
        Die "SHA-256 de $Asset não confere (esperado $expected, obtido $actual). Apague o download e rode o instalador de novo."
    }

    $other = Get-Command nix -ErrorAction SilentlyContinue
    if ($other -and $other.Source -and ($other.Source -ine $Dest)) {
        Write-Host "aviso: já existe um comando nix em $($other.Source)."
        Write-Host "Este binário entra na frente do PATH. Se você usa o gerenciador Nix (NixOS), chame-o pelo caminho absoluto."
    }

    New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
    Move-Item -Force (Join-Path $Work $Asset) $Dest
    Write-Host "nix-install: instalado em $Dest"

    $env:NIX_HOME = $Root
    $env:Path = "$BinDir;$env:Path"
    Write-Host "nix-install: aquecendo o cache do executável..."
    & $Dest --version
    if ($LASTEXITCODE -ne 0) {
        Remove-Item -Force $Dest -ErrorAction SilentlyContinue
        Die "O binário não executou (código $LASTEXITCODE). Permita nix.exe na Segurança do Windows e rode o instalador de novo."
    }

    Add-NixUserPath $Root
    Write-Host "NIX_HOME=$Root"
    Write-Host "Comando nix: $BinDir"

    $config = Join-Path $Root "settings.db"
    if (-not (Test-Path -LiteralPath $config)) {
        Write-Host "nix-install: iniciando configuração (nix init)..."
        & $Dest init @args
        if ($LASTEXITCODE -ne 0) { Stop-NixInstall $LASTEXITCODE }
    }
    else {
        Write-Host "settings.db já existe em $Root. O init não foi repetido."
        Write-Host "Para reconfigurar: nix init --vault CAMINHO"
    }

    Write-Host ""
    Write-Host "Abra um terminal novo. No MCP, command é $Dest"
}
finally {
    Remove-Item -Recurse -Force $Work -ErrorAction SilentlyContinue
}
