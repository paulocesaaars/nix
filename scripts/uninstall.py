"""Remove o PATH do Nix e apaga artefatos locais (.venv, .nix, nix.toml)."""

from __future__ import annotations

import os
import shutil
import stat
import sys
from collections.abc import Callable
from pathlib import Path

MIN_VERSION = (3, 11)
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from register_path import unregister_user_command  # noqa: E402

_HELP = """\
Remove NIX_HOME e o comando nix do PATH, apaga .venv e, salvo --keep-data,
apaga também .nix (índice, backups, logs) e nix.toml.
O vault do Obsidian e o código-fonte desta pasta não são alterados.

Uso:
  uninstall.bat
  uninstall.bat --yes
  uninstall.bat --keep-data --yes
"""


def _fail(message: str, code: int = 1) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(code)


def _parse(argv: list[str]) -> tuple[bool, bool]:
    yes = False
    keep_data = False
    for arg in argv:
        if arg in ("-h", "--help"):
            print(_HELP.strip())
            raise SystemExit(0)
        if arg in ("-y", "--yes"):
            yes = True
            continue
        if arg == "--keep-data":
            keep_data = True
            continue
        _fail(f"Argumento desconhecido: {arg}. Use --help.")
    return yes, keep_data


def _confirm() -> bool:
    if not sys.stdin.isatty():
        return False
    try:
        answer = input("Continuar? [s/N] ").strip().casefold()
    except EOFError:
        return False
    return answer in {"s", "sim", "y", "yes"}


def _retry_readonly(func: Callable[..., object], name: str, _exc: object) -> None:
    os.chmod(name, stat.S_IWRITE)
    func(name)


def _rmtree(path: Path) -> None:
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_retry_readonly)
    else:
        shutil.rmtree(path, onerror=_retry_readonly)


def _remove_path(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        if path.is_dir():
            _rmtree(path)
        else:
            path.unlink()
    except OSError as exc:
        return (
            f"{path}: {exc}. Feche programas que usem esta pasta "
            "(terminais, editor, servidor MCP) e rode o desinstalador de novo."
        )
    print(f"Removido: {path}")
    return None


def _local_targets(*, keep_data: bool) -> list[Path]:
    targets = [ROOT / ".venv"]
    targets.extend(sorted(ROOT.glob("*.egg-info")))
    targets.extend(sorted((ROOT / "src").glob("*.egg-info")))
    if not keep_data:
        targets.append(ROOT / ".nix")
        targets.append(ROOT / "nix.toml")
    return targets


def _print_plan(*, keep_data: bool) -> None:
    print("Nix — desinstalação")
    print(f"Pasta: {ROOT}")
    print()
    print("Será removido:")
    print("  - NIX_HOME e o comando nix do PATH do usuário")
    print("  - .venv")
    if keep_data:
        print("  (nix.toml e .nix serão mantidos por --keep-data)")
    else:
        print("  - .nix (índice, backups, logs)")
        print("  - nix.toml")
    print()
    print("Não será alterado:")
    print("  - o vault do Obsidian")
    print("  - o código-fonte desta pasta")
    print()
    print("O modelo de embedding (~2,3 GB) pode permanecer no cache do Hugging Face.")
    print("Se o editor ainda aponta para o Nix, remova o servidor do mcp.json.")


def main() -> None:
    yes, keep_data = _parse(sys.argv[1:])
    if sys.version_info < MIN_VERSION:
        found = ".".join(str(part) for part in sys.version_info[:3])
        required = f"{MIN_VERSION[0]}.{MIN_VERSION[1]}"
        _fail(
            f"Python {required}+ é necessário (encontrado {found}). "
            "Instale em https://www.python.org/downloads/ , "
            "marque 'Add python.exe to PATH' e rode o desinstalador de novo."
        )

    os.chdir(ROOT)
    _print_plan(keep_data=keep_data)
    if not yes and not _confirm():
        hint = "" if sys.stdin.isatty() else " Sem terminal interativo: passe --yes."
        _fail(f"Desinstalação cancelada.{hint}")

    print()
    print("Removendo NIX_HOME e o comando nix do PATH...")
    path_ok = unregister_user_command(ROOT)
    failures: list[str] = []
    for target in _local_targets(keep_data=keep_data):
        failed = _remove_path(target)
        if failed:
            failures.append(failed)

    if failures:
        for item in failures:
            print(f"[erro] {item}", file=sys.stderr)
        if not path_ok:
            _fail("A desinstalação não concluiu. Corrija os erros acima e tente de novo.")
        _fail("O PATH foi desfeito, mas alguns arquivos locais não puderam ser apagados.")

    print()
    if path_ok:
        print("Desinstalação concluída.")
    else:
        print("Arquivos locais removidos. O PATH permanente ainda precisa ser desfeito à mão.")


if __name__ == "__main__":
    main()
