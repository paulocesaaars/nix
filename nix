#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -x "$ROOT/.venv/bin/python" ]]; then
  exec "$ROOT/.venv/bin/python" -P -m nix "$@"
fi
if [[ -x "$ROOT/.venv/Scripts/python.exe" ]]; then
  exec "$ROOT/.venv/Scripts/python.exe" -P -m nix "$@"
fi

echo "[erro] Não achei .venv. Rode ./setup.sh nesta pasta primeiro." >&2
exit 1
