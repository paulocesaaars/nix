# Ativa `nix` neste terminal (não substitui o PATH permanente).
# Uso: . .\bin\env.ps1
$NixHome = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$env:NIX_HOME = $NixHome
$bin = Join-Path $NixHome "bin"
$already = $false
foreach ($part in ($env:Path -split [IO.Path]::PathSeparator)) {
    if (-not $part) { continue }
    if ($part.TrimEnd("\", "/") -ieq $bin.TrimEnd("\", "/")) {
        $already = $true
        break
    }
}
if (-not $already) {
    $env:Path = "$bin$([IO.Path]::PathSeparator)$($env:Path)"
}
