# Ativa `nix` neste terminal (não substitui o PATH permanente).
# Uso: source bin/env.sh
ROOT="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]:-$0}")/.." && pwd)"
export NIX_HOME="$ROOT"
chmod +x "$NIX_HOME/bin/nix" 2>/dev/null || true

_nix_bin="$NIX_HOME/bin"
_nix_bins=("$_nix_bin")
if command -v cygpath >/dev/null 2>&1; then
  _win="$(cygpath -w "$_nix_bin" 2>/dev/null || true)"
  _unix="$(cygpath -u "$_nix_bin" 2>/dev/null || true)"
  [[ -n "$_win" ]] && _nix_bins+=("$_win")
  [[ -n "$_unix" ]] && _nix_bins+=("$_unix")
fi

_nix_already=0
for _candidate in "${_nix_bins[@]}"; do
  case ":$PATH:" in
    *":${_candidate}:"*) _nix_already=1; break ;;
  esac
done
if [[ "$_nix_already" -eq 0 ]]; then
  export PATH="$_nix_bin:$PATH"
fi
unset _nix_bin _nix_bins _win _unix _nix_already _candidate
hash -r 2>/dev/null || true
