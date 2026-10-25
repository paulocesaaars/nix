"""Compila o binário único do Nix com Nuitka, na plataforma em que roda.

Exige Python 3.12 e o pacote já instalado neste ambiente (`pip install .`),
para o metadata de versão entrar no executável. O Nuitka não cruza sistema
operacional: cada release compila no runner da própria plataforma.

Uso:
  pip install "nuitka>=4.3.2,<5"
  python scripts/build_frozen.py
"""

from __future__ import annotations

import importlib.util
import os
import platform
import subprocess
import sys
import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENTRY = ROOT / "src" / "nix_frozen.py"
DIST = ROOT / "dist"

_PACKAGES = (
    "nix",
    "chromadb",
    "fastembed",
    "onnxruntime",
    "mcp",
    "tiktoken",
    "tokenizers",
    "huggingface_hub",
    "grpc",
)
# 4.3 inclui as tabelas unicode do Rich e o tratamento da dylib do onnxruntime no macOS.
_NUITKA_REQUIREMENT = "nuitka>=4.3.2,<5"
_NUITKA_MIN = (4, 3, 2)

_METADATA = (
    "nix",
    "chromadb",
    "fastembed",
    "onnxruntime",
    "mcp",
    "tiktoken",
    "tokenizers",
    "huggingface_hub",
    "numpy",
    "pydantic",
    "typer",
)


def _fail(message: str, code: int = 1) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(code)


def project_version() -> str:
    pyproject = ROOT / "pyproject.toml"
    with pyproject.open("rb") as handle:
        data = tomllib.load(handle)
    raw = data.get("project", {}).get("version")
    if not isinstance(raw, str) or not raw.strip():
        _fail(f"Não achei [project].version em {pyproject}.")
    return raw.strip()


def file_version(product: str) -> str:
    """Quatro números para o recurso de versão do Windows."""
    parts: list[str] = []
    for piece in product.split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        if not digits:
            break
        parts.append(str(int(digits)))
        if len(parts) == 3:
            break
    while len(parts) < 3:
        parts.append("0")
    return ".".join([*parts, "0"])


def target_ids() -> tuple[str, str]:
    system = {"win32": "windows", "linux": "linux", "darwin": "darwin"}.get(sys.platform)
    if system is None:
        _fail(
            f"Plataforma {sys.platform} sem binário. "
            "Compile em Windows, Linux ou macOS."
        )
    machine = platform.machine().lower()
    arch = {"amd64": "amd64", "x86_64": "amd64", "arm64": "arm64", "aarch64": "arm64"}.get(machine)
    if arch is None:
        _fail(
            f"Arquitetura {platform.machine()} sem binário. "
            "As publicadas são amd64 e arm64."
        )
    return system, arch


def asset_filename(product: str, system: str, arch: str) -> str:
    suffix = ".exe" if system == "windows" else ""
    return f"nix-{product}-{system}-{arch}{suffix}"


def _version_tuple(text: str) -> tuple[int, ...]:
    parts: list[int] = []
    for piece in text.split("."):
        digits = "".join(character for character in piece if character.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def _require_toolchain(product: str) -> None:
    if sys.version_info[:2] != (3, 12):
        found = sys.version.split()[0]
        _fail(
            f"O binário é compilado com Python 3.12 (encontrado {found}). "
            f"Crie um ambiente 3.12, rode `pip install .` e `pip install \"{_NUITKA_REQUIREMENT}\"`, "
            "e execute este script de novo."
        )
    try:
        installed = version("nix")
    except PackageNotFoundError:
        _fail("O pacote nix não está instalado neste ambiente. Rode `pip install .` e tente de novo.")
    if installed != product:
        _fail(
            f"A versão instalada do nix é {installed}, mas o pyproject.toml diz {product}. "
            "Rode `pip install .` neste ambiente e tente de novo."
        )
    if importlib.util.find_spec("nuitka") is None:
        _fail(
            "Nuitka não está instalado. "
            f'Rode `pip install "{_NUITKA_REQUIREMENT}"` e tente de novo.'
        )
    try:
        installed_nuitka = version("Nuitka")
    except PackageNotFoundError:
        _fail(
            "Nuitka não está instalado neste ambiente. "
            f'Rode `pip install "{_NUITKA_REQUIREMENT}"` e tente de novo.'
        )
    if _version_tuple(installed_nuitka) < _NUITKA_MIN:
        _fail(
            f"O Nuitka instalado é {installed_nuitka}. "
            f'Este build precisa de `{_NUITKA_REQUIREMENT}`. '
            f'Rode `pip install "{_NUITKA_REQUIREMENT}"` e tente de novo.'
        )


def _append_flags(env: dict[str, str], name: str, flags: str) -> None:
    current = env.get(name, "").strip()
    env[name] = f"{current} {flags}".strip()


def _linux_arm64_compiler_env() -> dict[str, str] | None:
    """Evita o estouro de R_AARCH64_CALL26 no ld do Ubuntu 24.04.

    O binutils anterior a 2.46 liga `--fix-cortex-a53-843419` por padrão e
    insere stubs de 4 KiB antes de posicionar os veneers. No texto gerado
    pelo Nuitka, esse deslocamento empurra o destino para fora do salto
    de ±128 MiB. Neste alvo o contorno do Cortex-A53 fica desligado.
    """
    if sys.platform != "linux" or platform.machine() not in {"aarch64", "arm64"}:
        return None
    env = os.environ.copy()
    cflags = "-mno-fix-cortex-a53-835769 -mno-fix-cortex-a53-843419"
    _append_flags(env, "CFLAGS", cflags)
    _append_flags(env, "CCFLAGS", cflags)
    _append_flags(env, "LDFLAGS", "-Wl,--no-fix-cortex-a53-843419")
    return env


def nuitka_command(product: str, filename: str) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "nuitka",
        "--mode=onefile",
        f"--output-dir={DIST}",
        f"--output-filename={filename}",
        "--lto=no",
        "--assume-yes-for-downloads",
        "--python-flag=no_site",
        "--python-flag=isolated",
        "--onefile-tempdir-spec={CACHE_DIR}/nix/onefile-{VERSION}",
        f"--product-version={product}",
        "--product-name=Nix",
        "--nofollow-import-to=pytest",
        "--nofollow-import-to=*.tests",
        "--include-module=nix_launch",
    ]
    for name in _PACKAGES:
        command.append(f"--include-package={name}")
        command.append(f"--include-package-data={name}")
    for name in _METADATA:
        command.append(f"--include-distribution-metadata={name}")
    if sys.platform == "win32":
        command.extend(
            [
                "--windows-console-mode=force",
                "--company-name=Nix",
                f"--file-version={file_version(product)}",
                "--file-description=Servidor MCP stdio para vaults do Obsidian",
            ]
        )
    command.append(str(ENTRY))
    return command


def main() -> None:
    if not ENTRY.is_file():
        _fail(f"Não achei {ENTRY}. Rode este script na árvore do repositório Nix.")
    product = project_version()
    _require_toolchain(product)
    system, arch = target_ids()
    filename = asset_filename(product, system, arch)
    DIST.mkdir(parents=True, exist_ok=True)
    for old in DIST.glob("nix-*"):
        if old.is_file():
            old.unlink()
    command = nuitka_command(product, filename)
    print("> " + " ".join(command))
    result = subprocess.run(command, cwd=ROOT, env=_linux_arm64_compiler_env())
    if result.returncode != 0:
        _fail(
            f"Nuitka falhou (código {result.returncode}). "
            "Veja o log acima, instale o compilador C da plataforma e rode de novo."
        )
    binary = DIST / filename
    if not binary.is_file():
        _fail(f"O Nuitka terminou sem gerar {binary}. Confira --output-filename e rode de novo.")
    (DIST / "asset-name.txt").write_text(filename + "\n", encoding="utf-8")
    print(f"Binário: {binary}")


if __name__ == "__main__":
    main()
