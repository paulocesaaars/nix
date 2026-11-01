#!/bin/sh
# Instala o binário do Nix (sem Python), grava NIX_HOME, coloca bin no PATH
# e inicia nix init se ainda não houver settings.db.
#
# Uso:
#   curl -fsSL https://raw.githubusercontent.com/paulocesaaars/nix/main/install.sh | sh
#   sh install.sh --vault "$HOME/Vault"
#
# Variáveis:
#   NIX_VERSION   tag da release (com ou sem o v inicial). Vazio = última estável.
#   NIX_HOME      pasta da instalação, se já estiver no ambiente.

set -eu

REPO="paulocesaaars/nix"
BASE_URL="https://github.com/${REPO}/releases/download"
MARKER_BEGIN="# >>> nix >>>"
MARKER_END="# <<< nix <<<"

die() {
  echo "nix-install: $1" >&2
  exit 1
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  cat <<'EOF'
Baixa o binário do Nix, grava NIX_HOME, coloca $NIX_HOME/bin no PATH e,
se não houver settings.db, executa nix init.

Argumentos extras vão para nix init, por exemplo:
  sh install.sh --vault "$HOME/Vault"

NIX_VERSION escolhe a release (ex.: 1.2.3 ou v1.2.3). Sem isso, vale a última estável.
EOF
  exit 0
fi

uname_s=$(uname -s)
case "$uname_s" in
  Linux) platform=linux ;;
  Darwin) platform=darwin ;;
  MINGW*|MSYS*|CYGWIN*)
    die "No Windows, rode install.ps1 ou install.bat."
    ;;
  *)
    die "Sistema ${uname_s} sem binário publicado. Use Windows amd64, Linux ou macOS Apple Silicon."
    ;;
esac

uname_m=$(uname -m)
case "$uname_m" in
  x86_64|amd64) arch=amd64 ;;
  arm64|aarch64) arch=arm64 ;;
  *)
    die "Arquitetura ${uname_m} sem binário publicado. As publicadas são amd64 e arm64."
    ;;
esac

if [ "$platform" = "darwin" ] && [ "$arch" = "amd64" ]; then
  die "macOS Intel (darwin-amd64) não tem binário publicado. Use um Mac Apple Silicon."
fi

default_root() {
  if [ "$platform" = "darwin" ]; then
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

sq_escape() {
  printf '%s' "$1" | sed "s/'/'\\\\''/g"
}

write_block() {
  escaped=$(sq_escape "$1")
  printf '%s\n' \
    "$MARKER_BEGIN" \
    "export NIX_HOME='$escaped'" \
    'case ":$PATH:" in *":$NIX_HOME/bin:"*) ;; *) export PATH="$NIX_HOME/bin:$PATH" ;; esac' \
    "$MARKER_END"
}

rc_targets() {
  found=0
  for name in .bashrc .zshrc .bash_profile .profile; do
    if [ -f "$HOME/$name" ]; then
      printf '%s\n' "$HOME/$name"
      found=1
    fi
  done
  if [ "$found" -eq 0 ]; then
    printf '%s\n' "$HOME/.bashrc"
  fi
}

upsert_rc() {
  file=$1
  block=$2
  tmp=$(mktemp)
  if [ -f "$file" ]; then
    awk '
      $0 == "# >>> nix >>>" { skip=1; next }
      $0 == "# <<< nix <<<" { skip=0; next }
      skip != 1 { print }
    ' "$file" > "$tmp"
  else
    : > "$tmp"
  fi
  printf '\n%s\n' "$block" >> "$tmp"
  mv "$tmp" "$file"
}

register_path() {
  block=$(write_block "$1")
  rc_targets | while IFS= read -r file; do
    upsert_rc "$file" "$block"
  done
}

tag=${NIX_VERSION:-}
workdir=$(mktemp -d)
trap 'rm -rf "$workdir"' EXIT

if [ -z "$tag" ]; then
  echo "nix-install: resolvendo a última release estável..."
  curl -fsSL -H "User-Agent: nix-install" -H "Accept: application/vnd.github+json" \
    -o "$workdir/release.json" \
    "https://api.github.com/repos/${REPO}/releases/latest" \
    || die "Não foi possível consultar a release. Defina NIX_VERSION (ex.: 1.2.3) ou tente de novo."
  tag=$(sed -n 's/.*"tag_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$workdir/release.json" | head -n 1)
fi
[ -n "$tag" ] || die "Não achei uma release estável. Publique uma tag vX.Y.Z ou defina NIX_VERSION."
case "$tag" in
  v*) ;;
  *) tag="v$tag" ;;
esac
version=${tag#v}
asset="nix-${version}-${platform}-${arch}"
hook_asset="nix-hook-${version}-${platform}-${arch}"

curl -fsSL -o "$workdir/checksums.txt" "${BASE_URL}/${tag}/checksums.txt" \
  || die "Não baixei checksums.txt da release ${tag}. Rode o instalador de novo quando a release estiver completa."

fetch_checked() {
  name=$1
  echo "nix-install: baixando ${name} (${tag})..."
  curl -fsSL -o "$workdir/$name" "${BASE_URL}/${tag}/${name}" \
    || die "Não baixei ${name} da release ${tag}. Confira NIX_VERSION e a conexão, e rode de novo."
  expected=$(awk -v asset="$name" '$2 == asset { print $1; exit }' "$workdir/checksums.txt")
  [ -n "$expected" ] || die "checksums.txt da release ${tag} não lista ${name}. Rode o instalador de novo quando a release estiver completa."
  if command -v sha256sum >/dev/null 2>&1; then
    actual=$(sha256sum "$workdir/$name" | awk '{print $1}')
  else
    actual=$(shasum -a 256 "$workdir/$name" | awk '{print $1}')
  fi
  expected=$(printf '%s' "$expected" | tr 'A-F' 'a-f')
  actual=$(printf '%s' "$actual" | tr 'A-F' 'a-f')
  [ "$expected" = "$actual" ] || die "SHA-256 de ${name} não confere (esperado ${expected}, obtido ${actual}). Rode o instalador de novo."
}

fetch_checked "$asset"
fetch_checked "$hook_asset"

found=$(command -v nix 2>/dev/null || true)
if [ -n "$found" ]; then
  case "$found" in
    "$root/bin/nix"|"$root/bin/nix.exe") ;;
    *)
      echo "aviso: já existe um comando nix em ${found}." >&2
      echo "Este binário entra na frente do PATH. Se você usa o gerenciador Nix (NixOS), chame-o pelo caminho absoluto." >&2
      ;;
  esac
fi

mkdir -p "$root/bin"
cp "$workdir/$asset" "$root/bin/nix"
cp "$workdir/$hook_asset" "$root/bin/nix-hook"
chmod +x "$root/bin/nix" "$root/bin/nix-hook"
if [ "$platform" = "darwin" ]; then
  xattr -d com.apple.quarantine "$root/bin/nix" "$root/bin/nix-hook" 2>/dev/null || true
fi
echo "nix-install: instalado em $root/bin/nix e $root/bin/nix-hook"

export NIX_HOME="$root"
export PATH="$root/bin:$PATH"

echo "nix-install: aquecendo o cache dos executáveis..."
if ! "$root/bin/nix" --version; then
  rm -f "$root/bin/nix" "$root/bin/nix-hook"
  die "O binário não executou. No macOS, rode o instalador de novo (ele tira a quarentena). Em outros sistemas, confira a mensagem acima."
fi
# stdin em /dev/null: `curl | sh` deixaria o hook ler o resto do script.
if ! "$root/bin/nix-hook" hook --event other --agent cursor </dev/null; then
  rm -f "$root/bin/nix" "$root/bin/nix-hook"
  die "O nix-hook não executou. No macOS, rode o instalador de novo (ele tira a quarentena). Em outros sistemas, confira a mensagem acima."
fi

if register_path "$root"; then
  echo "NIX_HOME=$root"
  echo "Comando nix: $root/bin"
else
  echo "A instalação segue. Registre NIX_HOME e o PATH à mão (README.md, seção Registrar NIX_HOME e o PATH à mão) e abra um terminal novo." >&2
fi

if [ ! -f "$root/settings.db" ]; then
  echo "nix-install: iniciando configuração (nix init)..."
  "$root/bin/nix" init "$@"
else
  echo "settings.db já existe em $root. O init não foi repetido."
  echo "Para reconfigurar: nix init --vault CAMINHO"
fi

echo
echo "Abra um terminal novo. No MCP, command é o caminho absoluto de $root/bin/nix"
