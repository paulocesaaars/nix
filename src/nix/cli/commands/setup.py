"""nix init e nix doctor."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

from nix.cli.deps import with_errors
from nix.cli.render import console, print_banner, print_embedding_choice_table
from nix.config.embedding_models import SUPPORTED_EMBEDDING_MODELS, default_embedding_model
from nix.config.store import SettingsStore
from nix.core.admin.doctor import DoctorCheck, build_doctor_report
from nix.core.admin.setup import initialize
from nix.core.admin.vaults import DEFAULT_VAULT_NAME
from nix.core.errors import ConfigError

_DEFAULT_EMBEDDING = default_embedding_model()


def _validate_embedding(raw: str) -> str:
    value = raw.strip().strip('"').strip("'")
    if value in SUPPORTED_EMBEDDING_MODELS:
        return value
    if value.isdigit():
        index = int(value)
        if 1 <= index <= len(SUPPORTED_EMBEDDING_MODELS):
            return SUPPORTED_EMBEDDING_MODELS[index - 1]
    allowed = ", ".join(SUPPORTED_EMBEDDING_MODELS)
    raise ConfigError(f"Modelo {value!r} não é suportado. Use um de: {allowed}.")


def _validate_vault(raw: str) -> Path:
    text = raw.strip().strip('"').strip("'")
    if not text:
        raise ConfigError(
            "O caminho do vault está vazio. Informe a pasta do Obsidian, por exemplo C:/Obsidian/MeuVault."
        )
    path = Path(text)
    if not path.exists():
        raise ConfigError(f"O caminho {path} não existe. Crie a pasta do vault ou informe outro caminho.")
    if not path.is_dir():
        raise ConfigError(f"{path} não é um diretório. Aponte para a pasta raiz do vault do Obsidian.")
    return path.resolve()


def _ask_vault() -> Path:
    console.print(
        "Informe a pasta do vault do Obsidian. No Windows use [cyan]/[/cyan] ([dim]C:/Obsidian/MeuVault[/dim])."
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


def _resolve_vault(explicit: str | None) -> Path:
    if explicit is not None and explicit.strip():
        return _validate_vault(explicit)
    if not sys.stdin.isatty():
        raise ConfigError("Sem terminal interativo. Passe o vault com `nix init --vault CAMINHO`.")
    return _ask_vault()


def _ask_embedding() -> str:
    console.print("Escolha o modelo de embedding (local, sem GPU). Comparação:")
    print_embedding_choice_table()
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


def _print_check(check: DoctorCheck) -> None:
    line = f"{check.label}: {check.message}"
    if check.level == "error":
        console.print(f"[red]{line}[/red]")
    elif check.level == "warn":
        console.print(f"[yellow]{line}[/yellow]")
    else:
        console.print(line)


@with_errors
def cmd_init(
    force: bool = typer.Option(False, "--force", help="Regrava a configuração do zero"),
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
    name: str | None = typer.Option(
        None,
        "--name",
        help=f"Nome do primeiro vault (sem --name, usa {DEFAULT_VAULT_NAME}). "
        "Se a configuração já tem vaults, use `nix vault add`.",
    ),
) -> None:
    print_banner(
        "[bold]Olá. Eu sou o Nix[/bold] — ponte MCP entre o vault e os agentes de desenvolvimento.\n"
        "[dim]Vamos apontar o vault e indexar as notas.[/dim]"
    )
    vault_path = _resolve_vault(vault)
    creating = force or not SettingsStore().is_initialized()
    model = _resolve_embedding(embedding_model, ask=creating)
    explicit_model = embedding_model is not None and bool(embedding_model.strip())
    result = initialize(
        vault=vault_path,
        embedding_model=model,
        force=force,
        update_embedding=creating or explicit_model,
        name=name,
    )
    console.print(f"Configuração em [bold]{result.settings_path}[/bold].")
    console.print(f"Vault [cyan]{result.vault_name}[/cyan] = {result.vault_path}")
    if result.embedding_written:
        console.print(f"[cyan]index.embedding_model[/cyan] = {json.dumps(result.embedding_model)}")
    if result.embedding_written and result.previously_initialized:
        console.print("[dim]Se o índice já existia com outro modelo, rode `nix sync --full`.[/dim]")
    console.print("[bold]Configuração concluída.[/bold]")


@with_errors
def cmd_doctor(
    as_json: bool = typer.Option(False, "--json", help="Relatório completo em JSON"),
) -> None:
    report = build_doctor_report()
    if as_json:
        console.print_json(json.dumps(report.to_dict(), ensure_ascii=False))
        return
    console.print(f"Nix {report.version} · Python {report.python}")
    if report.nix_home:
        console.print(f"NIX_HOME: {report.nix_home}")
    if report.command:
        console.print(f"comando nix: {report.command}")
    elif report.command_problem:
        console.print(f"[yellow]{report.command_problem}[/yellow]")
    if report.initialized:
        console.print(f"Config: {report.settings_path}")
    else:
        console.print(f"Config: {report.settings_path} (ainda não existe — rode `nix init`)")
    if report.config_error:
        console.print(f"[red]Falha ao carregar config: {report.config_error}[/red]")
    elif report.initialized and report.config is not None:
        console.print("Config carregada: ok")
        listed = (report.config or {}).get("vaults") if isinstance(report.config, dict) else None
        if isinstance(listed, list) and listed:
            for item in listed:
                if not isinstance(item, dict):
                    continue
                mark = " (padrão)" if item.get("is_default") else ""
                console.print(f"vault {item.get('name')}: {item.get('path')}{mark}")
        else:
            console.print(f"vault.path: {report.vault_path or '(vazio)'}")
        console.print(f"index.embedding_model: {report.embedding_model}")
        console.print(f"index.data_dir: {report.data_dir} → {report.data_path}")
    for check in report.checks:
        if check.label == "Config":
            continue
        _print_check(check)
