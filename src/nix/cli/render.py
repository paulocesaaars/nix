"""Saída Rich: banner, tabelas de sync/status e erros."""

from __future__ import annotations

from importlib.resources import files

from rich.console import Console
from rich.progress import Progress
from rich.table import Table

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


def apply_sync_progress(progress: Progress, event: SyncProgress) -> None:
    if not progress.tasks:
        return
    task_id = progress.tasks[0].id
    progress.update(
        task_id,
        total=max(event.total, 1),
        completed=event.current,
        description=f"{event.action} {event.rel_path}",
    )
