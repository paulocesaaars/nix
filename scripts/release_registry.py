"""Gera os MCPB da release e a ficha server.json.

No job de publicação, com os binários já compilados em `artifacts`:

  python scripts/release_registry.py pack --version 5.2.0 --artifacts artifacts
  sha256sum nix-* | tee checksums.txt
  python scripts/release_registry.py card --version 5.2.0 --tag v5.2.0 \\
      --repo paulocesaaars/nix --checksums checksums.txt --output server.json

O SHA de cada pacote é o que o `sha256sum` acabou de gravar. Este script não
recalcula o digest na hora de montar a ficha.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from nix.mcp.registry import RegistryError, pack_release, server_json  # noqa: E402


def _fail(message: str, code: int = 1) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(code)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Gera os MCPB da release e a ficha server.json.")
    sub = parser.add_subparsers(dest="command", required=True)

    pack = sub.add_parser("pack", help="gera um MCPB por plataforma a partir dos binários")
    pack.add_argument("--version", required=True, help="versão do pyproject, sem o v")
    pack.add_argument("--artifacts", required=True, type=Path, help="pasta com os binários compilados")
    pack.add_argument("--repo", default="paulocesaaars/nix", help="owner/nome do repositório da release")
    pack.add_argument(
        "--icon",
        type=Path,
        default=ROOT / "src" / "nix" / "mcp" / "nix.png",
        help="PNG embutido no MCPB (padrão: src/nix/mcp/nix.png)",
    )

    card = sub.add_parser("card", help="grava server.json com o SHA do passo dos checksums")
    card.add_argument("--version", required=True, help="versão do pyproject, sem o v")
    card.add_argument("--tag", required=True, help="tag da release, no formato vX.Y.Z")
    card.add_argument("--repo", required=True, help="owner/nome, como paulocesaaars/nix")
    card.add_argument("--checksums", required=True, type=Path, help="saída do sha256sum")
    card.add_argument("--output", required=True, type=Path, help="caminho do server.json")
    return parser


def main(argv: list[str] | None = None) -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = _parser().parse_args(argv)
    try:
        if args.command == "pack":
            written = pack_release(args.artifacts, args.version, args.icon, args.repo)
            for path in written:
                print(path)
            return
        text = args.checksums.read_text(encoding="utf-8")
        card = server_json(version=args.version, tag=args.tag, repo=args.repo, checksums=text)
        payload = json.dumps(card, ensure_ascii=False, indent=2) + "\n"
        args.output.write_text(payload, encoding="utf-8")
        print(args.output)
    except RegistryError as exc:
        _fail(str(exc))
    except OSError as exc:
        _fail(f"Não consegui ler ou gravar o arquivo ({exc}). Confira o caminho e tente de novo.")


if __name__ == "__main__":
    main()
