"""Cria o .venv, instala o Nix, registra o comando no PATH e inicia `nix init`."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

MIN_VERSION = (3, 11)
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "src"))

from register_path import register_user_command  # noqa: E402

from nix_launch import venv_python  # noqa: E402


def _fail(message: str, code: int = 1) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(code)


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
            "Cria o ambiente virtual .venv, instala os pacotes do Nix, "
            "registra NIX_HOME e o comando nix no PATH, e inicia nix init.\n"
            "Argumentos extras vão para nix init, por exemplo:\n"
            '  install.bat --vault "C:/Obsidian/MeuVault"'
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

    python = venv_python(ROOT)
    if python is not None:
        print("Ambiente .venv já existe. Reutilizando.")
    else:
        print("Criando ambiente virtual em .venv ...")
        _run([sys.executable, "-m", "venv", str(ROOT / ".venv")])
        python = venv_python(ROOT)
        if python is None:
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

    print("Registrando o comando nix no PATH do usuário...")
    if not register_user_command(ROOT):
        print(
            "A instalação segue. Registre NIX_HOME e o PATH à mão "
            "(INSTALL.md) e abra um terminal novo."
        )

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
