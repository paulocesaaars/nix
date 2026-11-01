"""nix init e nix doctor."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

from nix.cli.deps import with_errors
from nix.cli.render import (
    console,
    print_banner,
    print_doctor,
    print_embedding_choice_table,
    print_init_result,
    print_problem,
    print_step,
)
from nix.config.embedding_models import (
    EMBEDDING_MODELS,
    default_embedding_model,
    embedding_model_choices,
    resolve_embedding_model,
)
from nix.config.store import SettingsStore
from nix.core.admin.doctor import build_doctor_report
from nix.core.admin.setup import initialize
from nix.core.admin.wikis import DEFAULT_WIKI_NAME
from nix.core.errors import ConfigError

_DEFAULT_EMBEDDING = default_embedding_model()


def _validate_embedding(raw: str) -> str:
    """Aceita o id, a raça ou o número da tabela. Só o `nix init` usa o número."""
    text = raw.strip().strip('"').strip("'")
    if text.isdigit():
        index = int(text)
        if 1 <= index <= len(EMBEDDING_MODELS):
            return EMBEDDING_MODELS[index - 1].name
    resolved = resolve_embedding_model(text)
    if resolved is None:
        raise ConfigError(
            f"Modelo {text!r} não é suportado. Informe o número da tabela ou um de: {embedding_model_choices()}."
        )
    return resolved


def _validate_vault(raw: str) -> Path:
    text = raw.strip().strip('"').strip("'")
    if not text:
        raise ConfigError(
            "O caminho da wiki está vazio. Informe a pasta da wiki, por exemplo C:/Notas/MinhaWiki."
        )
    path = Path(text)
    if not path.exists():
        raise ConfigError(f"O caminho {path} não existe. Crie a pasta da wiki ou informe outro caminho.")
    if not path.is_dir():
        raise ConfigError(f"{path} não é um diretório. Aponte para a pasta raiz da wiki.")
    return path.resolve()


def _ask_vault(step: tuple[int, int]) -> Path:
    print_step(*step, "Wiki")
    console.print(
        " Informe a pasta da wiki. No Windows use [accent]/[/accent] ([dim]C:/Notas/MinhaWiki[/dim])."
    )
    while True:
        raw = typer.prompt("Caminho da wiki")
        try:
            path = Path(raw.strip().strip('"').strip("'"))
        except (OSError, RuntimeError):
            print_problem("Caminho inválido. Tente de novo.")
            continue
        if not path.exists():
            if typer.confirm(f"{path} não existe. Criar o diretório?", default=False):
                try:
                    path.mkdir(parents=True)
                except OSError as exc:
                    print_problem(f"Não foi possível criar {path}: {exc}")
                    continue
            else:
                continue
        if not path.is_dir():
            print_problem("Não é um diretório. Informe a pasta da wiki.")
            continue
        return path.resolve()


def _resolve_vault(explicit: str | None, step: tuple[int, int]) -> Path:
    if explicit is not None and explicit.strip():
        return _validate_vault(explicit)
    if not sys.stdin.isatty():
        raise ConfigError("Sem terminal interativo. Passe a wiki com `nix init --wiki CAMINHO`.")
    return _ask_vault(step)


def _ask_embedding(step: tuple[int, int]) -> str:
    print_step(*step, "Modelo de embedding")
    console.print(" Roda local, na CPU. Comparação:")
    console.print()
    print_embedding_choice_table()
    console.print(
        " [dim]A lulu é o padrão: sync mais rápido em computador com pouca folga. "
        "O spitz pede CPU, memória e disco de sobra, e melhora a busca.[/dim]"
    )
    while True:
        raw = typer.prompt("Modelo", default="1")
        try:
            return _validate_embedding(raw)
        except ConfigError as exc:
            print_problem(exc.message)


def _resolve_embedding(explicit: str | None, *, ask: bool, step: tuple[int, int]) -> str:
    if explicit is not None and explicit.strip():
        return _validate_embedding(explicit)
    if not ask:
        return _DEFAULT_EMBEDDING
    if not sys.stdin.isatty():
        return _DEFAULT_EMBEDDING
    return _ask_embedding(step)


@with_errors
def cmd_init(
    force: bool = typer.Option(False, "--force", help="Regrava a configuração do zero"),
    wiki: str | None = typer.Option(
        None,
        "--wiki",
        help="Caminho da wiki; se omitido, pergunta no terminal",
    ),
    embedding_model: str | None = typer.Option(
        None,
        "--embedding-model",
        help="Modelo de embedding (nome ou número da lista do init)",
    ),
    name: str | None = typer.Option(
        None,
        "--name",
        help=f"Nome da primeira wiki (sem --name, usa {DEFAULT_WIKI_NAME}). "
        "Se a configuração já tem wikis, use `nix wiki add`.",
    ),
) -> None:
    print_banner(
        "[bold]Olá. Eu sou o Nix[/bold] — ponte MCP entre a wiki e os agentes de desenvolvimento.\n"
        "[dim]Vamos apontar a wiki e indexar as notas.[/dim]"
    )
    creating = force or not SettingsStore().is_initialized()
    explicit_model = embedding_model is not None and bool(embedding_model.strip())
    # Só as perguntas que vão aparecer entram na contagem das etapas.
    interactive = sys.stdin.isatty()
    asks_vault = interactive and not (wiki is not None and wiki.strip())
    asks_model = interactive and creating and not explicit_model
    total = int(asks_vault) + int(asks_model)
    wiki_path = _resolve_vault(wiki, (1, total))
    model = _resolve_embedding(embedding_model, ask=creating, step=(int(asks_vault) + 1, total))
    result = initialize(
        wiki=wiki_path,
        embedding_model=model,
        force=force,
        update_embedding=creating or explicit_model,
        name=name,
    )
    print_init_result(result)


@with_errors
def cmd_doctor(
    as_json: bool = typer.Option(False, "--json", help="Relatório completo em JSON"),
) -> None:
    report = build_doctor_report()
    if as_json:
        console.print_json(json.dumps(report.to_dict(), ensure_ascii=False))
        return
    print_doctor(report)
