"""Confere o binário congelado antes de publicar a release.

Stdout de `nix --version` tem de ser só a versão, na primeira e na segunda
partida. Em seguida `nix init` e `nix doctor` exercitam o template e os
imports pesados, sem baixar o modelo ONNX.

Uso:
  python scripts/smoke_frozen.py dist/nix-1.2.3-windows-amd64.exe 1.2.3
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

_IMPORTS = ("chromadb", "fastembed", "mcp", "tiktoken")
_TIMEOUT_S = 600


def _fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def _version_text(stdout: str) -> str:
    return stdout.replace("\r\n", "\n").strip("\n")


def _capture(binary: Path, args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Lê stdout e stderr como UTF-8.

    No Windows o Python do runner decodifica o pipe com cp1252. O binário
    escreve UTF-8 (o doctor usa «·» e «→»), e um byte fora desse mapa
    derruba a thread de leitura antes do smoke ver o relatório.
    """
    return subprocess.run(
        [str(binary), *args],
        capture_output=True,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=_TIMEOUT_S,
        check=False,
    )


def _check_version(binary: Path, version: str, env: dict[str, str]) -> None:
    result = _capture(binary, ["--version"], env)
    stdout = _version_text(result.stdout)
    if result.returncode != 0 or stdout != version:
        _fail(
            "nix --version não emitiu só a versão no stdout.\n"
            f"  código: {result.returncode}\n"
            f"  stdout: {result.stdout!r}\n"
            f"  stderr: {result.stderr!r}\n"
            "O modo onefile não pode escrever no stdout: isso corrompe o MCP. "
            "Ajuste o bootstrap do Nuitka e compile de novo."
        )


def _run(binary: Path, args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    result = _capture(binary, args, env)
    if result.returncode != 0:
        _fail(
            f"`nix {' '.join(args)}` falhou (código {result.returncode}).\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def main() -> None:
    if len(sys.argv) != 3:
        _fail("Uso: python scripts/smoke_frozen.py <binário> <versão>")
    binary = Path(sys.argv[1])
    version = sys.argv[2].strip()
    if not binary.is_file():
        _fail(f"Não achei o binário {binary}. Compile com scripts/build_frozen.py e tente de novo.")
    if not version:
        _fail("A versão está vazia. Passe o valor de [project].version, sem o prefixo v.")

    with tempfile.TemporaryDirectory(prefix="nix-smoke-") as tmp:
        root = Path(tmp)
        home = root / "home"
        vault = root / "vault"
        home.mkdir()
        vault.mkdir()
        env = os.environ.copy()
        env["NIX_HOME"] = str(home)
        env.pop("NIX_CONFIG", None)
        env["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
        env["TQDM_DISABLE"] = "1"
        env["TOKENIZERS_PARALLELISM"] = "false"
        env["PYTHONIOENCODING"] = "utf-8"
        _check_version(binary, version, env)
        _check_version(binary, version, env)
        _run(binary, ["init", "--vault", str(vault)], env)
        doctor = _run(binary, ["doctor"], env)
        report = doctor.stdout
        missing = [label for label in _IMPORTS if f"Import {label}: ok" not in report]
        if missing:
            _fail(
                "nix doctor não confirmou os imports do binário: " + ", ".join(missing) + ".\n"
                f"stdout:\n{report}\nstderr:\n{doctor.stderr}\n"
                "Inclua o pacote que faltou no Nuitka e compile de novo."
            )
    print(f"Smoke ok: {binary}")


if __name__ == "__main__":
    main()
