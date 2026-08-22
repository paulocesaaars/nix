# Remove o Nix (PATH, venv, índice local). Não altera a sessão atual nem o vault.
# Uso: .\uninstall.ps1 [--yes] [--keep-data]
$NixSourced = ($MyInvocation.InvocationName -eq ".")
$Root = $PSScriptRoot
$Uninstall = Join-Path $Root "scripts\uninstall.py"

if (-not (Test-Path -LiteralPath $Uninstall)) {
    Write-Error "Não achei scripts/uninstall.py. Rode uninstall.ps1 na raiz do repositório Nix."
    if ($NixSourced) { return }
    exit 1
}

function Test-Python311 {
    param([string[]]$Command)
    $code = "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
    if ($Command.Length -eq 1) {
        & $Command[0] -c $code 2>$null
    }
    else {
        & $Command[0] $Command[1] -c $code 2>$null
    }
    return ($LASTEXITCODE -eq 0)
}

$PyCmd = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    if (Test-Python311 @("py", "-3")) { $PyCmd = @("py", "-3") }
}
if (-not $PyCmd -and (Get-Command python -ErrorAction SilentlyContinue)) {
    if (Test-Python311 @("python")) { $PyCmd = @("python") }
}
if (-not $PyCmd -and (Get-Command python3 -ErrorAction SilentlyContinue)) {
    if (Test-Python311 @("python3")) { $PyCmd = @("python3") }
}

if (-not $PyCmd) {
    Write-Error "Python 3.11+ não encontrado. Instale em https://www.python.org/downloads/ e marque 'Add python.exe to PATH'."
    if ($NixSourced) { return }
    exit 1
}

Write-Host "Nix — desinstalação"
Write-Host "Usando: $($PyCmd -join ' ')"

if ($PyCmd.Length -eq 1) {
    & $PyCmd[0] $Uninstall @args
}
else {
    & $PyCmd[0] $PyCmd[1] $Uninstall @args
}
if ($LASTEXITCODE -ne 0) {
    if ($NixSourced) { return }
    exit $LASTEXITCODE
}
