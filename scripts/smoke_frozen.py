"""Confere o binário congelado antes de publicar a release.

Stdout de `nix --version` tem de ser só a versão, na primeira e na segunda
partida. Em seguida `nix init` e `nix doctor` exercitam o template e os
imports pesados, sem baixar o modelo ONNX. Por fim, `nix hook` é cronometrado
(meta de 300 ms, HU-S9) e o `sessionStart` do Cursor tem de imprimir o
`additional_context` com o handoff (HU-S7).

Uso:
  python scripts/smoke_frozen.py dist/nix-1.2.3-windows-amd64.exe 1.2.3
"""

from __future__ import annotations

import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

_IMPORTS = ("chromadb", "fastembed", "mcp", "tiktoken")
_TIMEOUT_S = 600
_HOOK_BUDGET_MS = 300
_HOOK_RUNS = 5


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


def _hook(binary: Path, args: list[str], payload: dict[str, object], env: dict[str, str]) -> tuple[str, float]:
    """Roda `nix hook` com o JSON no stdin. Devolve o stdout e o tempo em ms."""
    started = time.perf_counter()
    result = subprocess.run(
        [str(binary), "hook", *args],
        input=json.dumps(payload),
        capture_output=True,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=_TIMEOUT_S,
        check=False,
    )
    elapsed = (time.perf_counter() - started) * 1000
    if result.returncode != 0:
        _fail(f"`nix hook {' '.join(args)}` terminou com código {result.returncode}; o hook tem de sair sempre com 0.")
    return result.stdout, elapsed


def _check_hook(binary: Path, root: Path, env: dict[str, str]) -> None:
    """HU-S9 (tempo do hook) e HU-S7 (`additional_context` no `sessionStart` do Cursor)."""
    project = root / "projeto"
    (project / ".git").mkdir(parents=True)
    _run(binary, ["hooks", "install", "--agent", "cursor", "--yes", "--project", str(project)], env)
    base: dict[str, object] = {"workspace_roots": [str(project)]}

    _hook(binary, ["--event", "user-prompt", "--agent", "cursor"], {**base, "conversation_id": "aquecer"}, env)
    times: list[float] = []
    for index in range(_HOOK_RUNS):
        payload = {**base, "conversation_id": "medir", "prompt": f"pedido {index}"}
        out, elapsed = _hook(binary, ["--event", "user-prompt", "--agent", "cursor"], payload, env)
        if out.strip():
            _fail(f"O hook de user-prompt não pode escrever no stdout, e escreveu: {out!r}.")
        times.append(elapsed)
    median = statistics.median(times)
    print(f"Hook: mediana de {median:.0f} ms em {_HOOK_RUNS} execuções (meta: {_HOOK_BUDGET_MS} ms).")
    if median > _HOOK_BUDGET_MS:
        _fail(
            f"O hook levou {median:.0f} ms, acima dos {_HOOK_BUDGET_MS} ms. Veja o que o ponto de entrada em "
            "nix_launch importa antes de `nix.core.sessions.hook_entry` e ative a fila do RF-135."
        )

    _hook(binary, ["--event", "session-end", "--agent", "cursor"], {**base, "conversation_id": "medir"}, env)
    time.sleep(2)  # o session-end dispara o consolidador em segundo plano
    out, _ = _hook(binary, ["--event", "session-start", "--agent", "cursor"], {**base, "conversation_id": "novo"}, env)
    try:
        context = json.loads(out)["additional_context"]
    except (ValueError, KeyError, TypeError):
        _fail(f"O sessionStart do Cursor não imprimiu o `additional_context` com o handoff. stdout: {out!r}")
    if "pedido 4" not in context:
        _fail(f"O handoff não traz o último pedido da sessão anterior: {context!r}")
    start = ["--event", "session-start", "--agent", "cursor"]
    again, _ = _hook(binary, start, {**base, "conversation_id": "outro"}, env)
    if again.strip():
        _fail("O handoff foi entregue duas vezes: o segundo sessionStart não podia receber nada.")
    print("Hook ok: additional_context entregue uma só vez.")


def main() -> None:
    if len(sys.argv) != 3:
        _fail("Uso: python scripts/smoke_frozen.py <binário> <versão>")
    binary = Path(sys.argv[1])
    version = sys.argv[2].strip()
    if not binary.is_file():
        _fail(f"Não achei o binário {binary}. Compile com scripts/build_frozen.py e tente de novo.")
    if not version:
        _fail("A versão está vazia. Passe o valor de [project].version, sem o prefixo v.")

    with tempfile.TemporaryDirectory(prefix="nix-smoke-", ignore_cleanup_errors=True) as tmp:
        root = Path(tmp)
        home = root / "home"
        vault = root / "vault"
        home.mkdir()
        vault.mkdir()
        env = os.environ.copy()
        env["NIX_HOME"] = str(home)
        env["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
        env["TQDM_DISABLE"] = "1"
        env["TOKENIZERS_PARALLELISM"] = "false"
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
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
        _check_hook(binary, root, env)
    print(f"Smoke ok: {binary}")


if __name__ == "__main__":
    main()
