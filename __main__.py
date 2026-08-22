"""Permite `python -m nix` a partir do projeto pai (pasta `nix/` no workspace).

O interpretador do sistema encontra este arquivo porque o diretório se chama
`nix`. Delegamos ao launcher, que relança o `.venv` e a CLI real.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from nix_launch import main

if __name__ == "__main__":
    main()
