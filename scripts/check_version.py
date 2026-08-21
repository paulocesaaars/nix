"""Confere se a versão da tag do release bate com a versão declarada no código."""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_PATTERN = re.compile(r'^__version__\s*=\s*["\'](?P<version>[^"\']+)["\']', re.MULTILINE)


def _fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def _pyproject_version() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = data.get("project", {}).get("version")
    if not isinstance(version, str):
        _fail("pyproject.toml não declara [project].version. Adicione a versão antes de publicar.")
    return version


def _package_version() -> str:
    source = (ROOT / "src" / "nix" / "__init__.py").read_text(encoding="utf-8")
    match = VERSION_PATTERN.search(source)
    if match is None:
        _fail("src/nix/__init__.py não declara __version__. Adicione a versão antes de publicar.")
    return match.group("version")


def main() -> None:
    if len(sys.argv) != 2:
        _fail("Uso: python scripts/check_version.py <versao>  (ex.: 0.1.0)")

    expected = sys.argv[1]
    divergences = {
        "pyproject.toml": _pyproject_version(),
        "src/nix/__init__.py": _package_version(),
    }
    wrong = {origin: found for origin, found in divergences.items() if found != expected}
    if wrong:
        detail = "; ".join(f"{origin} = {found}" for origin, found in wrong.items())
        _fail(
            f"A tag pede a versão {expected}, mas o código declara: {detail}. "
            f"Atualize a versão para {expected} nesses arquivos ou publique a tag v{divergences['pyproject.toml']}."
        )

    print(f"Versão {expected} confirmada em pyproject.toml e src/nix/__init__.py.")


if __name__ == "__main__":
    main()
