#!/usr/bin/env bash
# Remove o Nix (PATH, venv, índice local). Não altera a sessão atual nem o vault.
# Uso: bash uninstall.sh [--yes] [--keep-data]
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]:-$0}")" && pwd)"
UNINSTALL="$ROOT/scripts/uninstall.py"
if [[ ! -f "$UNINSTALL" ]]; then
  echo "[erro] Não achei scripts/uninstall.py. Rode uninstall.sh na raiz do repositório Nix." >&2
  exit 1
fi

pick_python() {
  local candidate
  for candidate in python3.14 python3.13 python3.12 python3.11 python3 python py; do
    if ! command -v "$candidate" >/dev/null 2>&1; then
      continue
    fi
    if "$candidate" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" 2>/dev/null; then
      printf '%s' "$candidate"
      return 0
    fi
  done
  return 1
}

PY="$(pick_python)" || {
  echo "[erro] Python 3.11+ não encontrado. Instale o Python 3.11 ou superior, deixe-o no PATH e tente de novo." >&2
  exit 1
}

echo "Usando: $PY"
"$PY" "$UNINSTALL" "$@"
