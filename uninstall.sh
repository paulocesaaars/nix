#!/bin/sh
# Remove o binário do Nix, NIX_HOME e o PATH. Não altera o vault.
# Uso: sh uninstall.sh [--yes] [--keep-data]
set -eu

die() {
  echo "nix-uninstall: $1" >&2
  exit 1
}

yes=0
keep=0
for arg in "$@"; do
  case "$arg" in
    -h|--help)
      cat <<'EOF'
Remove NIX_HOME e $NIX_HOME/bin do PATH se apontarem para esta instalação,
apaga o binário e, salvo --keep-data, apaga settings.db e .nix.
O vault do Obsidian não é alterado.

Uso:
  sh uninstall.sh
  sh uninstall.sh --yes
  sh uninstall.sh --keep-data --yes
EOF
      exit 0
      ;;
    -y|--yes) yes=1 ;;
    --keep-data) keep=1 ;;
    *) die "Argumento desconhecido: $arg. Use --help." ;;
  esac
done

uname_s=$(uname -s)
case "$uname_s" in
  MINGW*|MSYS*|CYGWIN*)
    die "No Windows, rode uninstall.ps1 ou uninstall.bat."
    ;;
esac

default_root() {
  if [ "$(uname -s)" = "Darwin" ]; then
    printf '%s\n' "$HOME/Library/Application Support/nix"
    return
  fi
  if [ -n "${XDG_DATA_HOME:-}" ]; then
    printf '%s\n' "$XDG_DATA_HOME/nix"
  else
    printf '%s\n' "$HOME/.local/share/nix"
  fi
}

rc_home() {
  for file in "$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.bash_profile" "$HOME/.profile"; do
    [ -f "$file" ] || continue
    line=$(grep '^export NIX_HOME=' "$file" 2>/dev/null | head -n 1 || true)
    [ -n "$line" ] || continue
    value=${line#export NIX_HOME=}
    value=$(printf '%s' "$value" | sed "s/^['\"]//; s/['\"]$//")
    if [ -n "$value" ]; then
      printf '%s\n' "$value"
      return 0
    fi
  done
  return 1
}

if [ -n "${NIX_HOME:-}" ]; then
  root=$NIX_HOME
elif root=$(rc_home); then
  :
else
  root=$(default_root)
fi

if [ "$yes" -ne 1 ]; then
  if [ ! -t 0 ]; then
    die "Sem terminal interativo. Rode de novo com --yes."
  fi
  echo "Isto remove o Nix em $root."
  if [ "$keep" -ne 1 ]; then
    echo "settings.db e .nix também serão apagados. O vault não."
  fi
  printf 'Continuar? [s/N] '
  read -r answer || answer=""
  case "$(printf '%s' "$answer" | tr '[:upper:]' '[:lower:]')" in
    s|sim|y|yes) ;;
    *)
      echo "Desinstalação cancelada."
      exit 0
      ;;
  esac
fi

strip_block() {
  file=$1
  tmp=$(mktemp)
  awk '
    $0 == "# >>> nix >>>" { skip=1; next }
    $0 == "# <<< nix <<<" { skip=0; next }
    skip != 1 { print }
  ' "$file" > "$tmp"
  mv "$tmp" "$file"
}

sq_escape() {
  printf '%s' "$1" | sed "s/'/'\\\\''/g"
}

needle_quoted="export NIX_HOME='$(sq_escape "$root")'"
needle_raw="export NIX_HOME=$root"
for file in "$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.bash_profile" "$HOME/.profile"; do
  if [ -f "$file" ] && { grep -F -x "$needle_quoted" "$file" >/dev/null 2>&1 || grep -F -x "$needle_raw" "$file" >/dev/null 2>&1; }; then
    strip_block "$file"
  fi
done

rm -f "$root/bin/nix" "$root/bin/nix.exe" "$root/bin/nix.cmd"
if [ -d "$root/bin" ]; then
  rmdir "$root/bin" 2>/dev/null || true
fi

if [ "$keep" -ne 1 ]; then
  rm -rf "$root/.nix"
  rm -f "$root/settings.db" "$root/settings.db-wal" "$root/settings.db-shm"
  echo "Binário, settings.db e .nix removidos de $root. O vault não foi alterado."
else
  echo "Binário removido de $root. settings.db e .nix foram preservados."
fi

echo "Abra um terminal novo: o comando nix desta instalação deixa de valer."
echo "Remova também o servidor nix do mcp.json do editor."
