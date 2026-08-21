"""nix init e doctor."""

from __future__ import annotations

import json
import re
import sys
from importlib.resources import files
from pathlib import Path

import typer

from nix.cli.deps import with_errors
from nix.cli.render import console, print_banner
from nix.config.loader import (
    default_config_path,
    load_config,
    public_dict,
    resolve_config_path,
)
from nix.core.errors import ConfigError

_PATH_LINE = re.compile(r"(?m)^path\s*=\s*.*$")


def _toml_path(path: Path) -> str:
    return json.dumps(path.expanduser().resolve().as_posix(), ensure_ascii=False)


def _apply_vault_path(text: str, vault: Path) -> str:
    line = f"path = {_toml_path(vault)}"
    updated, count = _PATH_LINE.subn(line, text, count=1)
    if count:
        return updated
    return text.replace("[vault]", f"[vault]\n{line}", 1)


def _validate_vault(raw: str) -> Path:
    text = raw.strip().strip('"').strip("'")
    if not text:
        raise ConfigError(
            "O caminho do vault está vazio. Informe a pasta do Obsidian, "
            "por exemplo C:/Users/voce/Vault."
        )
    path = Path(text).expanduser()
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
        "No Windows use [cyan]/[/cyan] ([dim]C:/Users/voce/Vault[/dim])."
    )
    while True:
        raw = typer.prompt("Caminho do vault")
        try:
            path = Path(raw.strip().strip('"').strip("'")).expanduser()
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


def _resolve_vault(explicit: str | None) -> Path:
    if explicit is not None and explicit.strip():
        return _validate_vault(explicit)
    if not sys.stdin.isatty():
        raise ConfigError(
            "Sem terminal interativo. Passe o vault com `nix init --vault CAMINHO`."
        )
    return _ask_vault()


@with_errors
def cmd_init(
    force: bool = typer.Option(False, "--force", help="Sobrescreve o arquivo existente"),
    vault: str | None = typer.Option(
        None,
        "--vault",
        help="Caminho do vault; se omitido, pergunta no terminal",
    ),
) -> None:
    dest = Path.home() / ".nix" / "config.toml"
    env_dest = resolve_config_path()
    if env_dest is not None and env_dest.exists() and not force:
        dest = env_dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    print_banner(
        "[bold]Olá. Eu sou o Nix[/bold] — ponte MCP entre o vault e os agentes de desenvolvimento.\n"
        "[dim]Vamos apontar o vault e indexar as notas.[/dim]"
    )
    vault_path = _resolve_vault(vault)
    if dest.exists() and not force:
        current = dest.read_text(encoding="utf-8")
        dest.write_text(_apply_vault_path(current, vault_path), encoding="utf-8")
        console.print(
            f"Configuração em [bold]{dest}[/bold]. "
            f"[cyan]vault.path[/cyan] = {_toml_path(vault_path)}"
        )
        console.print("Rode [cyan]nix doctor[/cyan] e [cyan]nix sync[/cyan].")
        return
    template = files("nix.config").joinpath("template.toml").read_text(encoding="utf-8")
    dest.write_text(_apply_vault_path(template, vault_path), encoding="utf-8")
    console.print(f"Arquivo criado em [bold]{dest}[/bold].")
    console.print(f"[cyan]vault.path[/cyan] = {_toml_path(vault_path)}")
    console.print("Rode [cyan]nix doctor[/cyan] e [cyan]nix sync[/cyan].")


@with_errors
def cmd_doctor(
    as_json: bool = typer.Option(False, "--json", help="Dump completo da configuração"),
) -> None:
    from nix import __version__

    console.print(f"Nix {__version__} · Python {sys.version.split()[0]}")
    path = resolve_config_path()
    if path:
        console.print(f"Config: {path}")
    else:
        console.print(f"Config: {default_config_path()} (ainda não existe — rode `nix init`)")
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
        console.print(f"index.data_dir: {config.index.data_dir}")
        for warning in config.legacy_warnings:
            console.print(f"[yellow]{warning}[/yellow]")
    try:
        root = config.require_vault()
        console.print(f"Vault: {root} ok")
    except ConfigError as exc:
        console.print(f"[yellow]Vault: {exc.message}[/yellow]")
    for mod in ("chromadb", "fastembed", "mcp", "tiktoken"):
        try:
            __import__(mod)
            console.print(f"Import {mod}: ok")
        except Exception as exc:  # noqa: BLE001
            console.print(
                f"[red]Import {mod} falhou: {exc}. "
                "Rode `pip install -r requirements.txt`.[/red]"
            )
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
