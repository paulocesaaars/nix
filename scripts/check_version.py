"""Confere se a versão da tag do release bate com a versão declarada no pyproject.toml."""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def _pyproject_version() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = data.get("project", {}).get("version")
    if not isinstance(version, str):
        _fail("pyproject.toml não declara [project].version. Adicione a versão antes de publicar.")
    return version


def main() -> None:
    if len(sys.argv) != 2:
        _fail("Uso: python scripts/check_version.py <versao>  (ex.: 1.0.0)")

    expected = sys.argv[1]
    declared = _pyproject_version()
    if declared != expected:
        _fail(
            f"A tag pede a versão {expected}, mas o pyproject.toml declara {declared}. "
            f"Troque [project].version para {expected} e recrie a tag, "
            f"ou publique a tag v{declared}."
        )

    print(f"Versão {expected} confirmada no pyproject.toml.")


if __name__ == "__main__":
    main()
