"""Diagnóstico de ambiente, configuração e índice. Sem saída no terminal."""

from __future__ import annotations

import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from nix.config.loader import load_config, public_dict
from nix.config.paths import app_root, env_home, is_packaged, settings_path
from nix.config.store import SettingsStore
from nix.core.errors import ConfigError, NixError
from nix.core.models import IndexStatus

Level = Literal["ok", "warn", "error"]


@dataclass(frozen=True)
class DoctorCheck:
    label: str
    level: Level
    message: str


@dataclass
class DoctorReport:
    version: str
    python: str
    nix_home: str | None
    command: str | None
    command_problem: str | None
    settings_path: str
    initialized: bool
    config_error: str | None
    vault_path: str | None
    embedding_model: str | None
    data_dir: str | None
    data_path: str | None
    config: dict[str, Any] | None
    checks: list[DoctorCheck]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def session_activate_hint() -> str:
    root = app_root()
    sh = (root / "bin" / "env.sh").as_posix()
    cmd = str(root / "bin" / "env.cmd")
    ps1 = str(root / "bin" / "env.ps1")
    return f"source {sh} (Git Bash/Unix), call {cmd} (cmd) ou . {ps1} (PowerShell)"


def build_doctor_report(
    *,
    index_status: IndexStatus | None = None,
    index_problem: str | None = None,
    inspect_index: bool = True,
) -> DoctorReport:
    from nix import __version__

    checks: list[DoctorCheck] = []
    store = SettingsStore()
    initialized = False
    config_error: str | None = None
    try:
        initialized = store.is_initialized()
    except ConfigError as exc:
        config_error = exc.message

    nix_config = None
    config: dict[str, Any] | None = None
    if config_error is None:
        try:
            nix_config = load_config(use_cache=False)
            config = public_dict(nix_config)
        except (ConfigError, NixError) as exc:
            config_error = exc.message

    if not initialized and config_error is None:
        checks.append(
            DoctorCheck("Config", "warn", f"{store.path} ainda não existe. Rode `nix init`.")
        )
    elif config_error is not None:
        checks.append(DoctorCheck("Config", "error", config_error))

    home_path = env_home()
    command, command_problem = _command(home_path is not None)
    vault_ok = False
    if nix_config is not None:
        try:
            root = nix_config.require_vault()
            vault_ok = True
            checks.append(DoctorCheck("Vault", "ok", f"{root} ok"))
        except ConfigError as exc:
            checks.append(DoctorCheck("Vault", "warn", exc.message))

    _native_checks(checks)
    _import_checks(checks)
    _tokenizer_check(checks)
    if nix_config is not None:
        _data_dir_check(checks, nix_config.index.data_path)
        if not inspect_index:
            _index_supplied(checks, index_status, index_problem)
        elif vault_ok:
            _index_check(checks, nix_config)

    return DoctorReport(
        version=__version__,
        python=sys.version.split()[0],
        nix_home=str(home_path) if home_path is not None else None,
        command=command,
        command_problem=command_problem,
        settings_path=str(settings_path()),
        initialized=initialized,
        config_error=config_error,
        vault_path=nix_config.vault.path if nix_config is not None else None,
        embedding_model=nix_config.index.embedding_model if nix_config is not None else None,
        data_dir=nix_config.index.data_dir if nix_config is not None else None,
        data_path=str(nix_config.index.data_path) if nix_config is not None else None,
        config=config,
        checks=checks,
    )


def nix_command() -> tuple[str | None, str | None]:
    """Executável que sobe o servidor MCP e, se não achar, a ação corretiva."""
    return _command(env_home() is not None)


def _command(has_home: bool) -> tuple[str | None, str | None]:
    if is_packaged():
        return str(Path(sys.argv[0]).resolve()), None
    nix_cmd = shutil.which("nix") or shutil.which("nix.cmd")
    if nix_cmd:
        return nix_cmd, None
    hint = session_activate_hint()
    if not has_home:
        return None, f"NIX_HOME ausente e `nix` não está no PATH desta sessão. Rode `{hint}`."
    return None, f"comando `nix` não está no PATH desta sessão. Rode `{hint}`."


def _native_checks(checks: list[DoctorCheck]) -> None:
    from nix.core.index.native_compat import mmh3_is_stub, native_extension_remedy, prepare_native_imports

    prepare_native_imports()
    if mmh3_is_stub():
        checks.append(
            DoctorCheck(
                "mmh3",
                "warn",
                "stub (só para o FastEmbed importar). "
                f"Se o ChromaDB precisar do hash nativo: {native_extension_remedy()}",
            )
        )


def _import_checks(checks: list[DoctorCheck]) -> None:
    imports: tuple[tuple[str, str], ...] = (
        ("chromadb", "chromadb"),
        ("fastembed", "fastembed.text.text_embedding"),
        ("mcp", "mcp"),
        ("tiktoken", "tiktoken"),
    )
    for label, module in imports:
        try:
            __import__(module)
        except Exception as exc:  # noqa: BLE001
            checks.append(DoctorCheck(f"Import {label}", "error", f"falhou: {exc}. {_import_fix_hint(label, exc)}"))
        else:
            checks.append(DoctorCheck(f"Import {label}", "ok", "ok"))


def _tokenizer_check(checks: list[DoctorCheck]) -> None:
    from nix.core.index.tokenize import TokenCounter, approximate_tokenizer_hint

    if TokenCounter().approximate:
        checks.append(DoctorCheck("Tokens", "warn", approximate_tokenizer_hint()))
    else:
        checks.append(DoctorCheck("Tokens", "ok", "tiktoken"))


def _data_dir_check(checks: list[DoctorCheck], data: Path) -> None:
    try:
        data.mkdir(parents=True, exist_ok=True)
        probe = data / ".nix-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        checks.append(
            DoctorCheck(
                "data_dir",
                "error",
                f"Não foi possível escrever em {data}: {exc}. Ajuste index.data_dir.",
            )
        )
        return
    checks.append(DoctorCheck("data_dir", "ok", f"gravável: {data}"))


def _index_check(checks: list[DoctorCheck], config: Any) -> None:
    from nix.core.runtime import Runtime

    try:
        runtime = Runtime.from_config(config)
        try:
            status = runtime.status()
        finally:
            runtime.close()
    except Exception as exc:  # noqa: BLE001
        checks.append(DoctorCheck("Índice", "warn", f"ainda não utilizável: {exc}"))
        return
    checks.append(DoctorCheck("Índice", "ok", _index_message(status)))


def _index_supplied(
    checks: list[DoctorCheck],
    status: IndexStatus | None,
    problem: str | None,
) -> None:
    if problem:
        checks.append(DoctorCheck("Índice", "warn", problem))
        return
    if status is None:
        checks.append(
            DoctorCheck(
                "Índice",
                "warn",
                "Não foi possível ler o índice deste processo. Atualize o diagnóstico.",
            )
        )
        return
    checks.append(DoctorCheck("Índice", "ok", _index_message(status)))


def _index_message(status: IndexStatus) -> str:
    return f"{status.files} notas, {status.chunks} chunks, stale={status.stale}"


def _import_fix_hint(mod: str, exc: BaseException) -> str:
    from nix.core.index.native_compat import native_extension_remedy

    text = str(exc)
    blocked = "DLL" in text or "Controle de Aplicativo" in text or "Application Control" in text
    if blocked:
        extra = f"O Windows bloqueou a extensão nativa. {native_extension_remedy()}"
        if mod == "tiktoken":
            extra += " O chunking segue com contagem aproximada."
        if mod == "chromadb":
            extra += (
                " O Chroma 1.x puxa cygrpc só por causa do OpenTelemetry; "
                "o Nix tenta contornar isso no load."
            )
            if not is_packaged():
                extra += " Se o doctor ainda falhar, recrie o ambiente com Python 3.12."
        return extra
    if is_packaged():
        return (
            "O binário não carregou o módulo. Rode install.ps1 ou install.sh de novo "
            "para substituir o executável."
        )
    return "Rode `pip install -r requirements.txt`."
