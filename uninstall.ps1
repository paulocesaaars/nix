# Remove o binário do Nix, NIX_HOME e o PATH. Não altera o vault.
# Uso: .\uninstall.ps1 [--yes] [--keep-data]
$ErrorActionPreference = "Stop"
$script:NixSourced = ($MyInvocation.InvocationName -eq ".")

function Stop-NixInstall([int]$Code) {
    if ($script:NixSourced) { throw "nix-uninstall exit $Code" }
    exit $Code
}

function Die([string]$Message) {
    [Console]::Error.WriteLine("nix-uninstall: $Message")
    Stop-NixInstall 1
}

$Yes = $false
$KeepData = $false
foreach ($arg in $args) {
    if ($arg -in @("-h", "--help")) {
        Write-Host @"
Remove NIX_HOME e {NIX_HOME}\bin do PATH se apontarem para esta instalação,
apaga o binário, o cache de extração (onefile-* e hook-*) e, salvo --keep-data,
apaga settings.db e .nix. Se a pasta da instalação ficar vazia, ela também sai.
O vault do Obsidian não é alterado.

Uso:
  .\uninstall.ps1
  .\uninstall.ps1 --yes
  .\uninstall.ps1 --keep-data --yes
"@
        Stop-NixInstall 0
    }
    elseif ($arg -in @("-y", "--yes")) { $Yes = $true }
    elseif ($arg -eq "--keep-data") { $KeepData = $true }
    else { Die "Argumento desconhecido: $arg. Use --help." }
}

function Get-InstallRoot {
    $stored = [Environment]::GetEnvironmentVariable("NIX_HOME", "User")
    if ($env:NIX_HOME) { $stored = $env:NIX_HOME }
    if ($stored) { return $stored }
    if (-not $env:LOCALAPPDATA) {
        Die "LOCALAPPDATA não está definida e NIX_HOME está vazio. Defina NIX_HOME e rode de novo."
    }
    return (Join-Path $env:LOCALAPPDATA "nix")
}

function Same-Path([string]$Left, [string]$Right) {
    if (-not $Left -or -not $Right) { return $false }
    $a = [IO.Path]::GetFullPath($Left).TrimEnd("\").ToLower()
    $b = [IO.Path]::GetFullPath($Right).TrimEnd("\").ToLower()
    return $a -eq $b
}

function Remove-NixUserPath([string]$Root, [bool]$RemoveExpand) {
    $bin = (Join-Path $Root "bin").TrimEnd("\")
    $current = [Environment]::GetEnvironmentVariable("Path", "User")
    if (-not $current) { return }
    $kept = New-Object System.Collections.Generic.List[string]
    foreach ($raw in ($current -split ";")) {
        $token = $raw.Trim().Trim('"')
        if (-not $token) { continue }
        $normalized = $token.Replace("/", "\").TrimEnd("\")
        if ($RemoveExpand -and ($normalized -ieq "%NIX_HOME%\bin")) { continue }
        $expanded = [Environment]::ExpandEnvironmentVariables($token).TrimEnd("\")
        if ($expanded -ieq $bin) { continue }
        $kept.Add($raw)
    }
    $updated = ($kept -join ";")
    if ($updated -ne $current) {
        [Environment]::SetEnvironmentVariable("Path", $updated, "User")
    }
}

function Remove-NixRcBlock([string]$Path, [string]$Root) {
    if (-not (Test-Path -LiteralPath $Path)) { return }
    $text = [IO.File]::ReadAllText($Path)
    $begin = "# >>> nix >>>"
    $end = "# <<< nix <<<"
    $start = $text.IndexOf($begin)
    $stop = $text.IndexOf($end)
    if ($start -lt 0 -or $stop -lt $start) { return }
    $block = $text.Substring($start, $stop - $start)
    if ($block.IndexOf($Root) -lt 0) { return }
    $after = $stop + $end.Length
    if ($after -lt $text.Length -and $text[$after] -eq "`n") { $after++ }
    $updated = ($text.Substring(0, $start) + $text.Substring($after)).Trim()
    if ($updated) { $updated += "`n" }
    [IO.File]::WriteAllText($Path, $updated)
}

$Root = Get-InstallRoot
$Stored = [Environment]::GetEnvironmentVariable("NIX_HOME", "User")
$Ours = -not $Stored -or (Same-Path $Stored $Root)

if (-not $Yes) {
    $interactive = [Environment]::UserInteractive -and -not [Console]::IsInputRedirected
    if (-not $interactive) {
        Die "Sem terminal interativo. Rode de novo com --yes."
    }
    Write-Host "Isto remove o Nix em $Root."
    Write-Host "O cache de extração (onefile-* e hook-*) também será apagado."
    if (-not $KeepData) { Write-Host "settings.db e .nix também serão apagados. O vault não." }
    $answer = Read-Host "Continuar? [s/N]"
    if ($answer.Trim().ToLower() -notin @("s", "sim", "y", "yes")) {
        Write-Host "Desinstalação cancelada."
        Stop-NixInstall 0
    }
}

Write-Host "Removendo NIX_HOME e o comando nix do PATH..."
Remove-NixUserPath $Root $Ours
if ($Stored -and (Same-Path $Stored $Root)) {
    [Environment]::SetEnvironmentVariable("NIX_HOME", $null, "User")
}
foreach ($name in @(".bashrc", ".zshrc", ".bash_profile", ".profile")) {
    Remove-NixRcBlock (Join-Path $env:USERPROFILE $name) $Root
}

$bin = Join-Path $Root "bin"
foreach ($file in @("nix.exe", "nix", "nix.cmd", "nix-hook.exe", "nix-hook")) {
    $path = Join-Path $bin $file
    if (Test-Path -LiteralPath $path) { Remove-Item -Force -LiteralPath $path }
}
if ((Test-Path -LiteralPath $bin) -and -not (Get-ChildItem -Force -LiteralPath $bin | Select-Object -First 1)) {
    Remove-Item -Force -LiteralPath $bin
}

if (-not $KeepData) {
    foreach ($name in @("settings.db", "settings.db-wal", "settings.db-shm")) {
        $path = Join-Path $Root $name
        if (Test-Path -LiteralPath $path) { Remove-Item -Force -LiteralPath $path }
    }
    $nixDir = Join-Path $Root ".nix"
    if (Test-Path -LiteralPath $nixDir) { Remove-Item -Recurse -Force -LiteralPath $nixDir }
}

function Remove-NixExtractionCache([string]$Dir) {
    if (-not $Dir -or -not (Test-Path -LiteralPath $Dir)) { return }
    Get-ChildItem -Force -LiteralPath $Dir -Directory | ForEach-Object {
        if ($_.Name -like "onefile-*" -or $_.Name -like "hook-*") {
            Remove-Item -Recurse -Force -LiteralPath $_.FullName
        }
    }
    if ((Test-Path -LiteralPath $Dir) -and -not (Get-ChildItem -Force -LiteralPath $Dir | Select-Object -First 1)) {
        Remove-Item -Force -LiteralPath $Dir
    }
}

Remove-NixExtractionCache $Root
if ($env:LOCALAPPDATA) {
    $Cache = Join-Path $env:LOCALAPPDATA "nix"
    if (-not (Same-Path $Cache $Root)) { Remove-NixExtractionCache $Cache }
}

if (-not $KeepData) {
    if (Test-Path -LiteralPath $Root) {
        Write-Host "Binário, settings.db, .nix e o cache de extração removidos de $Root. O vault não foi alterado."
    }
    else {
        Write-Host "Binário, settings.db, .nix e o cache de extração removidos. A pasta $Root foi apagada. O vault não foi alterado."
    }
}
else {
    Write-Host "Binário e cache de extração removidos de $Root. settings.db e .nix foram preservados."
}

Write-Host "Abra um terminal novo: o comando nix desta instalação deixa de valer."
Write-Host "Remova também o servidor nix do mcp.json do editor."
