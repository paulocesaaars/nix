"""Cria o .venv, instala o Nix e inicia a configuração (`nix init`)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

MIN_VERSION = (3, 11)
ROOT = Path(__file__).resolve().parent.parent


def _fail(message: str, code: int = 1) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(code)


def _venv_python(root: Path) -> Path:
    windows = root / ".venv" / "Scripts" / "python.exe"
    if windows.exists():
        return windows
    return root / ".venv" / "bin" / "python"


def _run(cmd: list[str]) -> None:
    printable = " ".join(cmd)
    print(f"> {printable}")
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        _fail(
            f"Comando falhou (código {result.returncode}): {printable}. "
            "Corrija o erro acima e rode o instalador de novo."
        )


def main() -> None:
    extra = sys.argv[1:]
    if extra in (["-h"], ["--help"]):
        print(
            "Cria o ambiente virtual .venv, instala os pacotes do Nix "
            "e inicia nix init.\n"
            "Argumentos extras vão para nix init, por exemplo:\n"
            '  setup.bat --vault "C:/Users/voce/Vault"'
        )
        return

    if sys.version_info < MIN_VERSION:
        found = ".".join(str(part) for part in sys.version_info[:3])
        required = f"{MIN_VERSION[0]}.{MIN_VERSION[1]}"
        _fail(
            f"Python {required}+ é necessário (encontrado {found}). "
            "Instale em https://www.python.org/downloads/ , "
            "marque 'Add python.exe to PATH' e rode o instalador de novo."
        )

    os.chdir(ROOT)
    requirements = ROOT / "requirements.txt"
    if not requirements.is_file():
        _fail(
            f"Não achei {requirements}. "
            "Rode o instalador na raiz do repositório Nix."
        )

    python = _venv_python(ROOT)
    if python.exists():
        print("Ambiente .venv já existe. Reutilizando.")
    else:
        print("Criando ambiente virtual em .venv ...")
        _run([sys.executable, "-m", "venv", str(ROOT / ".venv")])
        python = _venv_python(ROOT)
        if not python.exists():
            _fail(
                "O ambiente .venv foi criado, mas o interpretador não apareceu. "
                "Apague a pasta .venv e rode o instalador de novo."
            )

    print("Atualizando pip...")
    _run([str(python), "-m", "pip", "install", "--upgrade", "pip"])
    print("Instalando pacotes do projeto...")
    _run([str(python), "-m", "pip", "install", "-r", str(requirements)])
    print("Instalando o Nix em modo editável...")
    _run([str(python), "-m", "pip", "install", "-e", "."])

    print("Iniciando configuração (nix init)...")
    try:
        result = subprocess.run(
            [str(python), "-P", "-m", "nix", "init", *extra],
            cwd=ROOT,
        )
    except KeyboardInterrupt:
        _fail("Instalação interrompida.", 130)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
