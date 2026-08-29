"""nix init e doctor."""

from __future__ import annotations

import json
import re
import shutil
import sys
from importlib.resources import files
from pathlib import Path

import typer

from nix.cli.deps import with_errors
from nix.cli.render import console, print_banner
from nix.config.loader import config_write_path, load_config, public_dict, resolve_config_path
from nix.config.paths import app_root, env_home
from nix.config.schema import EMBEDDING_MODEL_OPTIONS, SUPPORTED_EMBEDDING_MODELS
from nix.core.errors import ConfigError

_PATH_LINE = re.compile(r"(?m)^path\s*=\s*.*$")
_EMBED_LINE = re.compile(r"(?m)^embedding_model\s*=\s*.*$")
_DEFAULT_EMBEDDING = SUPPORTED_EMBEDDING_MODELS[0]


def _toml_path(path: Path) -> str:
    return json.dumps(path.resolve().as_posix(), ensure_ascii=False)


def _apply_vault_path(text: str, vault: Path) -> str:
    line = f"path = {_toml_path(vault)}"
    updated, count = _PATH_LINE.subn(line, text, count=1)
    if count:
        return updated
    return text.replace("[vault]", f"[vault]\n{line}", 1)


def _apply_embedding_model(text: str, model: str) -> str:
    line = f"embedding_model = {json.dumps(model, ensure_ascii=False)}"
    updated, count = _EMBED_LINE.subn(line, text, count=1)
    if count:
        return updated
    return text.replace("[index]", f"[index]\n{line}", 1)


def _validate_embedding(raw: str) -> str:
    value = raw.strip().strip('"').strip("'")
    if value in SUPPORTED_EMBEDDING_MODELS:
        return value
    if value.isdigit():
        index = int(value)
        if 1 <= index <= len(SUPPORTED_EMBEDDING_MODELS):
            return SUPPORTED_EMBEDDING_MODELS[index - 1]
    allowed = ", ".join(SUPPORTED_EMBEDDING_MODELS)
    raise ConfigError(
        f"Modelo {value!r} não é suportado. Use um de: {allowed}."
    )


def _validate_vault(raw: str) -> Path:
    text = raw.strip().strip('"').strip("'")
    if not text:
        raise ConfigError(
            "O caminho do vault está vazio. Informe a pasta do Obsidian, "
            "por exemplo C:/Obsidian/MeuVault."
        )
    path = Path(text)
    if not path.exists():
        raise ConfigError(
            f"O caminho {path} não existe. Crie a pasta do vault ou informe outro caminho."
        )
    if not path.is_dir():
        raise ConfigError(
            f"{path} não é um diretório. Aponte para a pasta raiz do vault do Obsidian."
        )
    return path.resolve()


def _ask_vault() -> Path:
    console.print(
        "Informe a pasta do vault do Obsidian. "
        "No Windows use [cyan]/[/cyan] ([dim]C:/Obsidian/MeuVault[/dim])."
    )
    while True:
        raw = typer.prompt("Caminho do vault")
        try:
            path = Path(raw.strip().strip('"').strip("'"))
        except (OSError, RuntimeError):
            console.print("[red]Caminho inválido. Tente de novo.[/red]")
            continue
        if not path.exists():
            if typer.confirm(f"{path} não existe. Criar o diretório?", default=False):
                try:
                    path.mkdir(parents=True)
                except OSError as exc:
                    console.print(f"[red]Não foi possível criar {path}: {exc}[/red]")
                    continue
            else:
                continue
        if not path.is_dir():
            console.print("[red]Não é um diretório. Informe a pasta do vault.[/red]")
            continue
        return path.resolve()


def _import_fix_hint(mod: str, exc: BaseException) -> str:
    text = str(exc)
    blocked = "DLL" in text or "Controle de Aplicativo" in text or "Application Control" in text
    if blocked:
        extra = (
            "O Windows bloqueou a extensão nativa. Em Segurança do Windows, "
            "permita o arquivo .pyd da pasta .venv ou recrie o ambiente."
        )
        if mod == "tiktoken":
            extra += " O chunking segue com contagem aproximada."
        return extra
    return "Rode `pip install -r requirements.txt`."


def _print_next_steps() -> None:
    console.print("[bold]Configuração concluída.[/bold]")


def _session_activate_hint() -> str:
    root = app_root()
    sh = (root / "bin" / "env.sh").as_posix()
    cmd = str(root / "bin" / "env.cmd")
    ps1 = str(root / "bin" / "env.ps1")
    return f"source {sh} (Git Bash/Unix), call {cmd} (cmd) ou . {ps1} (PowerShell)"


def _resolve_vault(explicit: str | None) -> Path:
    if explicit is not None and explicit.strip():
        return _validate_vault(explicit)
    if not sys.stdin.isatty():
        raise ConfigError(
            "Sem terminal interativo. Passe o vault com `nix init --vault CAMINHO`."
        )
    return _ask_vault()


def _ask_embedding() -> str:
    from rich.table import Table

    console.print("Escolha o modelo de embedding (local, sem GPU). Comparação:")
    table = Table(show_header=True, header_style="bold")
    table.add_column("#", style="cyan", justify="right")
    table.add_column("Modelo")
    table.add_column("Disco")
    table.add_column("Idiomas")
    table.add_column("CPU")
    table.add_column("Quando usar")
    for index, opt in enumerate(EMBEDDING_MODEL_OPTIONS, start=1):
        label = opt.name
        if index == 1:
            label = f"{opt.name} (padrão)"
        table.add_row(str(index), label, opt.size, opt.languages, opt.cpu, opt.use_when)
    console.print(table)
    console.print(
        "[dim]Máquina fraca + português: opção 2. "
        "Só inglês e sync rápido: 3 ou 4. "
        "Melhor qualidade e disco/RAM sobrando: 1.[/dim]"
    )
    while True:
        raw = typer.prompt("Modelo", default="1")
        try:
            return _validate_embedding(raw)
        except ConfigError as exc:
            console.print(f"[red]{exc.message}[/red]")


def _resolve_embedding(explicit: str | None, *, ask: bool) -> str:
    if explicit is not None and explicit.strip():
        return _validate_embedding(explicit)
    if not ask:
        return _DEFAULT_EMBEDDING
    if not sys.stdin.isatty():
        return _DEFAULT_EMBEDDING
    return _ask_embedding()


@with_errors
def cmd_init(
    force: bool = typer.Option(False, "--force", help="Sobrescreve o arquivo existente"),
    vault: str | None = typer.Option(
        None,
        "--vault",
        help="Caminho do vault; se omitido, pergunta no terminal",
    ),
    embedding_model: str | None = typer.Option(
        None,
        "--embedding-model",
        help="Modelo de embedding (nome ou número da lista do init)",
    ),
) -> None:
    dest = config_write_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    print_banner(
        "[bold]Olá. Eu sou o Nix[/bold] — ponte MCP entre o vault e os agentes de desenvolvimento.\n"
        "[dim]Vamos apontar o vault e indexar as notas.[/dim]"
    )
    vault_path = _resolve_vault(vault)
    creating = force or not dest.exists()
    model = _resolve_embedding(embedding_model, ask=creating)
    if dest.exists() and not force:
        current = dest.read_text(encoding="utf-8")
        current = _apply_vault_path(current, vault_path)
        if embedding_model is not None and embedding_model.strip():
            current = _apply_embedding_model(current, model)
        dest.write_text(current, encoding="utf-8")
        console.print(
            f"Configuração em [bold]{dest}[/bold]. "
            f"[cyan]vault.path[/cyan] = {_toml_path(vault_path)}"
        )
        if embedding_model is not None and embedding_model.strip():
            console.print(f"[cyan]index.embedding_model[/cyan] = {json.dumps(model)}")
            console.print(
                "[dim]Se o índice já existia com outro modelo, rode `nix sync --full`.[/dim]"
            )
        _print_next_steps()
        return
    template = files("nix.config").joinpath("template.toml").read_text(encoding="utf-8")
    text = _apply_vault_path(template, vault_path)
    text = _apply_embedding_model(text, model)
    dest.write_text(text, encoding="utf-8")
    console.print(f"Arquivo criado em [bold]{dest}[/bold].")
    console.print(f"[cyan]vault.path[/cyan] = {_toml_path(vault_path)}")
    console.print(f"[cyan]index.embedding_model[/cyan] = {json.dumps(model)}")
    _print_next_steps()


@with_errors
def cmd_doctor(
    as_json: bool = typer.Option(False, "--json", help="Dump completo da configuração"),
) -> None:
    from nix import __version__

    console.print(f"Nix {__version__} · Python {sys.version.split()[0]}")
    home_path = env_home()
    home = str(home_path) if home_path is not None else ""
    nix_cmd = shutil.which("nix") or shutil.which("nix.cmd")
    if home:
        console.print(f"NIX_HOME: {home}")
    if nix_cmd:
        console.print(f"comando nix: {nix_cmd}")
    elif not home:
        console.print(
            f"[yellow]NIX_HOME ausente e `nix` não está no PATH desta sessão. "
            f"Rode `{_session_activate_hint()}`.[/yellow]"
        )
    else:
        console.print(
            f"[yellow]comando `nix` não está no PATH desta sessão. "
            f"Rode `{_session_activate_hint()}`.[/yellow]"
        )
    path = resolve_config_path()
    if path:
        console.print(f"Config: {path}")
    else:
        console.print(f"Config: {config_write_path()} (ainda não existe — rode `nix init`)")
    try:
        config = load_config()
        console.print("Config carregada: ok")
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Falha ao carregar config: {exc}[/red]")
        return
    if as_json:
        dumped = public_dict(config)
        dumped["unknown_sections"] = list(config.unknown_sections)
        dumped["legacy_warnings"] = list(config.legacy_warnings)
        console.print_json(json.dumps(dumped, ensure_ascii=False, indent=2))
    else:
        console.print(f"vault.path: {config.vault.path or '(vazio)'}")
        console.print(f"index.embedding_model: {config.index.embedding_model}")
        console.print(f"index.data_dir: {config.index.data_dir} → {config.index.data_path}")
        for warning in config.legacy_warnings:
            console.print(f"[yellow]{warning}[/yellow]")
    try:
        root = config.require_vault()
        console.print(f"Vault: {root} ok")
    except ConfigError as exc:
        console.print(f"[yellow]Vault: {exc.message}[/yellow]")
    from nix.core.index.native_compat import allow_blocked_mmh3

    allow_blocked_mmh3()
    imports: tuple[tuple[str, str], ...] = (
        ("chromadb", "chromadb"),
        ("fastembed", "fastembed.text.text_embedding"),
        ("mcp", "mcp"),
        ("tiktoken", "tiktoken"),
    )
    for label, module in imports:
        try:
            __import__(module)
            console.print(f"Import {label}: ok")
        except Exception as exc:  # noqa: BLE001
            hint = _import_fix_hint(label, exc)
            console.print(f"[red]Import {label} falhou: {exc}. {hint}[/red]")
    data = config.index.data_path
    try:
        data.mkdir(parents=True, exist_ok=True)
        probe = data / ".nix-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        console.print(f"data_dir gravável: {data}")
    except OSError as exc:
        console.print(
            f"[red]Não foi possível escrever em {data}: {exc}. "
            "Ajuste index.data_dir.[/red]"
        )
    try:
        from nix.cli.deps import get_runtime

        runtime = get_runtime()
        status = runtime.status()
        console.print(
            f"Índice: {status.files} notas, {status.chunks} chunks, "
            f"stale={status.stale}"
        )
        runtime.close()
    except Exception as exc:  # noqa: BLE001
        console.print(f"[yellow]Índice ainda não utilizável: {exc}[/yellow]")
