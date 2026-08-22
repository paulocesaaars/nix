"""Ponto de entrada agnóstico ao diretório de trabalho.

Quando o Nix vive em `projeto/nix/`, o CWD do cliente MCP e da CLI costuma
ser o workspace pai. Nesse caso `python -m nix` enxerga a pasta do repositório
em vez do pacote instalado. Este módulo relança o Python do `.venv` se
preciso, tira o sombreamento do `sys.path` e delega à CLI.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def find_checkout_root(start: Path) -> Path | None:
    """Sobe a partir de `start` até achar `pyproject.toml` + `src/nix`."""
    try:
        resolved = start.resolve()
    except OSError:
        resolved = start
    for parent in [resolved, *resolved.parents]:
        if (parent / "src" / "nix" / "__init__.py").is_file() and (parent / "pyproject.toml").is_file():
            return parent
    return None


def checkout_root() -> Path:
    """Raiz do checkout (pasta com `src/` e `pyproject.toml`)."""
    found = find_checkout_root(Path(__file__).resolve())
    if found is not None:
        return found
    here = Path(__file__).resolve()
    if here.parent.name == "src":
        return here.parent.parent
    return here.parent


def venv_python(root: Path | None = None) -> Path | None:
    """Interpretador do `.venv` local, se existir."""
    base = root if root is not None else checkout_root()
    windows = base / ".venv" / "Scripts" / "python.exe"
    unix = base / ".venv" / "bin" / "python"
    if windows.is_file():
        return windows
    if unix.is_file():
        return unix
    return None


def _resolved(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path


def _is_real_package(directory: Path) -> bool:
    return (directory / "cli" / "app.py").is_file()


def _loaded_nix_is_real() -> bool:
    module = sys.modules.get("nix")
    origin = getattr(module, "__file__", None)
    if not origin:
        return False
    return _is_real_package(Path(origin).resolve().parent)


def unshadow() -> None:
    """Garante que `import nix` carrega o pacote em `src/nix`, não o checkout."""
    root = checkout_root()
    src = root / "src"
    cwd = _resolved(Path.cwd())
    blocked: set[str] = set()

    def block(path: Path) -> None:
        blocked.add(str(_resolved(path)).casefold())

    shadow = cwd / "nix"
    if shadow.is_dir() and not _is_real_package(shadow):
        block(cwd)
    if root.is_dir() and not _is_real_package(root):
        block(root)

    cleaned: list[str] = []
    for entry in sys.path:
        raw = entry if entry else str(cwd)
        try:
            resolved = _resolved(Path(raw))
        except (OSError, ValueError):
            cleaned.append(entry)
            continue
        if str(resolved).casefold() in blocked:
            continue
        if (
            resolved.name.casefold() == "nix"
            and resolved.is_dir()
            and not _is_real_package(resolved)
        ):
            continue
        cleaned.append(entry)
    sys.path[:] = cleaned

    src_str = str(src)
    if src.is_dir() and src_str not in sys.path:
        sys.path.insert(0, src_str)

    if "nix" in sys.modules and not _loaded_nix_is_real():
        for name in list(sys.modules):
            if name == "nix" or name.startswith("nix."):
                del sys.modules[name]


def _same_python(candidate: Path) -> bool:
    return _resolved(Path(sys.executable)) == _resolved(candidate)


def main() -> None:
    python = venv_python()
    if python is not None and not _same_python(python):
        cmd = [str(python), "-P", "-m", "nix", *sys.argv[1:]]
        raise SystemExit(subprocess.run(cmd).returncode)

    unshadow()
    try:
        from nix.cli.app import main as cli_main
    except ImportError:
        sys.stderr.write(
            "Pacote Nix não importável. Rode setup.bat ou ./setup.sh "
            "na pasta do Nix (cria o .venv e instala o pacote).\n"
        )
        raise SystemExit(1) from None
    cli_main()


if __name__ == "__main__":
    main()
