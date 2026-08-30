"""Saída Rich: banner, tabelas de sync/status e erros."""

from __future__ import annotations

from importlib.resources import files

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from nix.config.embedding_models import spec_for
from nix.core.index.tokenize import APPROXIMATE_TOKENIZER_HINT
from nix.core.models import IndexStatus, SyncProgress

console = Console()
err_console = Console(stderr=True)


def print_banner(message: str | None = None) -> None:
    try:
        art = files("nix.cli").joinpath("ascii-art.txt").read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError, OSError):
        art = "Nix"
    console.print(art.rstrip("\n"), highlight=False, markup=False, emoji=False)
    if message:
        console.print()
        console.print(message)


def print_error(message: str) -> None:
    err_console.print(f"[bold red]Erro:[/bold red] {message}")


def print_status(status: IndexStatus) -> None:
    table = Table(title="Índice Nix", show_header=False)
    table.add_column("Campo")
    table.add_column("Valor")
    table.add_row("Notas indexadas", str(status.files))
    table.add_row("Chunks", str(status.chunks))
    table.add_row("Erros", str(status.errors))
    table.add_row("Último sync", status.last_sync_at or "nunca")
    table.add_row("Embedding", status.embedding_model or "—")
    table.add_row("Vault", status.vault_path or "—")
    table.add_row("Dados", status.data_dir or "—")
    table.add_row("Defasado", "sim" if status.stale else "não")
    console.print(table)
    if status.stale_reason:
        console.print(f"[yellow]{status.stale_reason}[/yellow]")


def sync_progress() -> Progress:
    """Barra com spinner: em CPU o arquivo atual pode ficar parado vários minutos."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    )


def apply_sync_progress(progress: Progress, event: SyncProgress) -> None:
    if not progress.tasks:
        return
    task_id = progress.tasks[0].id
    if event.action == "load_model":
        model = event.detail
        spec = spec_for(model)
        size_bit = f"; 1ª vez: download {spec.size_label}" if spec is not None else ""
        description = f"Carregando {model}{size_bit}; em CPU pode demorar"
        completed = 0
    else:
        description = f"{event.action} {event.rel_path}"
        completed = event.current
    progress.update(
        task_id,
        total=max(event.total, 1),
        completed=completed,
        description=description,
    )


def print_tokenizer_warning(*, approximate: bool) -> None:
    if approximate:
        console.print(f"[yellow]{APPROXIMATE_TOKENIZER_HINT}[/yellow]")


def print_embedding_choice_table() -> None:
    from nix.cli.embedding_copy import labeled_model_rows

    table = Table(show_header=True, header_style="bold")
    table.add_column("#", style="cyan", justify="right")
    table.add_column("Modelo")
    table.add_column("Disco")
    table.add_column("Idiomas")
    table.add_column("CPU")
    table.add_column("Quando usar")
    for index, (spec, copy) in enumerate(labeled_model_rows(), start=1):
        short = f"{spec.short_name} (padrão)" if index == 1 else spec.short_name
        table.add_row(
            str(index),
            f"{short}\n[dim]{spec.name}[/dim]",
            spec.size_label,
            copy.languages,
            copy.cpu,
            copy.use_when,
        )
    console.print(table)
