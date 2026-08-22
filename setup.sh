#!/usr/bin/env bash
# Instala o Nix (venv, PATH, nix init). Não altera a sessão atual.
# Uso: ./setup.sh
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]:-$0}")" && pwd)"
BOOTSTRAP="$ROOT/scripts/bootstrap.py"
if [[ ! -f "$BOOTSTRAP" ]]; then
  echo "[erro] Não achei scripts/bootstrap.py. Rode setup.sh na raiz do repositório Nix." >&2
  exit 1
fi

pick_python() {
  local candidate
  for candidate in python3.13 python3.12 python3.11 python3 python py; do
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

echo "Nix — instalação do ambiente e configuração"
echo "Usando: $PY"
chmod +x "$ROOT/bin/nix" 2>/dev/null || true

"$PY" "$BOOTSTRAP" "$@"

echo
echo "O comando nix vale num terminal novo."
