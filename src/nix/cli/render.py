"""Saída Rich da CLI: tema, componentes de tela e o resultado de cada comando."""

from __future__ import annotations

import json
from importlib.resources import files
from typing import TYPE_CHECKING

from rich import box
from rich.console import Console, Group, RenderableType
from rich.markup import escape
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from nix.config.embedding_models import spec_for
from nix.core.index.tokenize import approximate_tokenizer_hint
from nix.core.models import IndexStatus, SyncProgress, SyncReport

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from nix.config.editor import ConfigEntry
    from nix.config.schema import VaultSettings
    from nix.config.store import SettingsChange
    from nix.core.admin.doctor import DoctorReport
    from nix.core.admin.setup import InitResult

# Cores do DESIGN.md: acento e cores de status. O texto normal e o `dim` seguem o
# tema do terminal, porque o fundo é do usuário.
NIX_THEME = Theme(
    {
        "accent": "#FF385C",
        "accent.strong": "bold #FF385C",
        "success": "#04694A",
        "warning": "#8A5300",
        "error": "#C13515",
        "bar.complete": "#FF385C",
        "bar.finished": "#04694A",
        "bar.pulse": "#FF385C",
        "progress.spinner": "#FF385C",
    }
)

console = Console(theme=NIX_THEME)
err_console = Console(stderr=True, theme=NIX_THEME)


def print_banner(message: str | None = None) -> None:
    try:
        art = files("nix.cli").joinpath("ascii-art.txt").read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError, OSError):
        art = "Nix"
    console.print(art.rstrip("\n"), style="bright_white", highlight=False, markup=False, emoji=False)
    if message:
        console.print()
        console.print(message)


def print_error(message: str) -> None:
    err_console.print(f"[bold][error]Erro:[/error][/bold] {escape(message)}")


def _marks() -> dict[str, str]:
    """Marcas de resultado; ASCII quando o terminal não é UTF-8."""
    if "utf" in (console.encoding or "").lower():
        return {"ok": "✓", "warn": "⚠", "fail": "✗", "run": "●"}
    return {"ok": "+", "warn": "!", "fail": "x", "run": "*"}


_STATE = {"ok": ("ok", "success"), "warn": ("warn", "warning"), "fail": ("fail", "error"), "run": ("run", "accent")}


def _state_line(kind: str, text: str, detail: str | None = None) -> Text:
    """Linha de situação: marca e texto no estilo do tipo (`ok`, `warn`, `fail`, `run`)."""
    mark_key, style = _STATE[kind]
    line = Text()
    line.append(f"{_marks()[mark_key]} ", style=style)
    line.append(text, style=style)
    if detail:
        line.append(f" · {detail}", style="dim")
    return line


def _cell(value: object) -> Text:
    """Célula com texto literal: colchetes de caminhos e nomes não viram marcação Rich."""
    return Text(str(value))


def _kv_grid() -> Table:
    """Grade de duas colunas: rótulo em cinza e valor."""
    grid = Table.grid(padding=(0, 3))
    grid.add_column(style="dim", no_wrap=True)
    grid.add_column(overflow="fold")
    return grid


def _count(value: int) -> str:
    """Milhar com ponto, como no restante da interface em português."""
    return f"{value:,}".replace(",", ".")


def _panel(body: RenderableType, title: str | Text, *, expand: bool = False) -> Panel:
    heading = title if isinstance(title, Text) else Text(title, style="bold")
    return Panel(body, title=heading, title_align="left", box=box.ROUNDED, padding=(1, 2), expand=expand)


def print_header(detail: str | None = None) -> None:
    """Cabeçalho curto de um comando: nome, versão e, se houver, o contexto."""
    from nix import __version__

    line = Text.assemble((" nix ", "accent.strong"), (f"v{__version__}", "dim"))
    if detail:
        line.append(f" · {detail}", style="dim")
    console.print(line)
    console.print()


def print_status(status: IndexStatus, *, vault: str | None = None) -> None:
    if status.errors:
        state = _state_line("fail", f"{status.errors} nota(s) com erro")
    elif status.stale:
        state = _state_line("warn", "Desatualizado")
    else:
        state = _state_line("ok", "Em dia")
    if status.stale and status.stale_reason:
        state.append(f" · {status.stale_reason}", style="dim")

    grid = _kv_grid()
    grid.add_row("Notas", _count(status.files))
    if status.sessions:
        grid.add_row("Sessões", _count(status.sessions))
    grid.add_row("Trechos", _count(status.chunks))
    grid.add_row("Último sync", _cell(status.last_sync_at or "nunca"))
    grid.add_row("Embedding", _cell(status.embedding_model or "—"))
    grid.add_row("Vault", _cell(status.vault_path or "—"))
    grid.add_row("Dados", _cell(status.data_dir or "—"))

    heading = Text.assemble((f"{_marks()['run']} ", "accent"), ("Índice" if not vault else f"Índice · {vault}", "bold"))
    console.print(_panel(Group(state, Text(), grid), heading))

    if status.stale or not status.last_sync_at:
        target = f" --vault {escape(vault)}" if vault else ""
        console.print(f" [dim]Próximo passo:[/dim] nix sync{target}")


def print_doctor(report: DoctorReport) -> None:
    """Diagnóstico em dois painéis: o ambiente e as verificações, com o resumo no fim."""
    print_header("diagnóstico")

    env = _kv_grid()
    env.add_row("Nix", _cell(f"{report.version} · Python {report.python}"))
    if report.nix_home:
        env.add_row("NIX_HOME", _cell(report.nix_home))
    if report.command:
        env.add_row("Comando", _cell(report.command))
    elif report.command_problem:
        env.add_row("Comando", Text(report.command_problem, style="warning"))
    if report.initialized:
        env.add_row("Config", _cell(report.settings_path))
    else:
        env.add_row("Config", Text(f"{report.settings_path} (não existe)", style="warning"))
    if report.initialized and report.config is not None and not report.config_error:
        listed = report.config.get("vaults")
        if isinstance(listed, list) and listed:
            for item in listed:
                if isinstance(item, dict):
                    tail = "  (padrão)" if item.get("is_default") else ""
                    env.add_row("Vault", _cell(f"{item.get('name')} · {item.get('path')}{tail}"))
        else:
            env.add_row("Vault", _cell(report.vault_path or "(vazio)"))
        env.add_row("Embedding", _cell(report.embedding_model or "—"))
        env.add_row("Dados", _cell(f"{report.data_dir} → {report.data_path}"))
    console.print(_panel(env, "Ambiente"))

    checks = Table.grid(padding=(0, 2))
    checks.add_column(no_wrap=True)
    checks.add_column(style="bold", no_wrap=True)
    checks.add_column(overflow="fold")
    for check in report.checks:
        kind = "fail" if check.level == "error" else check.level
        mark_key, style = _STATE[kind]
        message_style = "" if check.level == "ok" else style
        mark = Text(_marks()[mark_key], style=style)
        checks.add_row(mark, _cell(check.label), Text(check.message, style=message_style))
    console.print(_panel(checks, "Verificações"))

    counts = report.counts()
    summary = Text(" ")
    summary.append(f"{counts['ok']} ok", style="success")
    summary.append(" · ", style="dim")
    summary.append(f"{counts['warn']} aviso(s)", style="warning" if counts["warn"] else "dim")
    summary.append(" · ", style="dim")
    summary.append(f"{counts['error']} erro(s)", style="error" if counts["error"] else "dim")
    console.print(summary)
    if not report.initialized:
        console.print(" [dim]Próximo passo:[/dim] nix init")


_ACTION_STYLE = {"add": ("+", "success"), "update": ("~", "accent"), "remove": ("-", "error")}


def print_sync_report(
    name: str,
    root: str | Path,
    excludes: list[str],
    report: SyncReport,
    events: list[SyncProgress],
    dry_run: bool,
) -> None:
    """Resultado de um vault: situação, contagens, arquivos tocados e erros."""
    seconds = f"{report.elapsed_seconds:.1f}".replace(".", ",")
    if dry_run:
        state = _state_line("run", "Pré-visualização")
        state.append(" · nada foi gravado", style="dim")
    elif report.failed:
        state = _state_line("warn", f"Concluído com {report.failed} erro(s) em {seconds} s")
    else:
        state = _state_line("ok", f"Concluído em {seconds} s")

    grid = _kv_grid()
    grid.add_row("Adicionadas" if not dry_run else "Seriam adicionadas", _count(report.added))
    grid.add_row("Atualizadas" if not dry_run else "Seriam atualizadas", _count(report.updated))
    grid.add_row("Removidas" if not dry_run else "Seriam removidas", _count(report.removed))
    grid.add_row("Inalteradas", _count(report.skipped))
    if report.failed:
        grid.add_row("Com erro", Text(_count(report.failed), style="error"))
    if not dry_run:
        chunks = Text(_count(report.chunks_created))
        if report.chunks_reused:
            chunks.append(
                f"  ({_count(report.chunks_reused)} reaproveitados, {_count(report.chunks_embedded)} vetorizados)",
                style="dim",
            )
        grid.add_row("Trechos", chunks)
    grid.add_row("Vault", _cell(root))

    console.print(_panel(Group(state, Text(), grid), name))
    print_tokenizer_warning(approximate=report.tokenizer_approximate)

    touched = [event for event in events if event.action != "load_model"]
    if touched:
        console.print(" [dim]Arquivos[/dim]")
        for event in touched:
            sign, style = _ACTION_STYLE.get(event.action, ("·", "dim"))
            where = f"{event.vault} " if event.vault else ""
            console.print(Text.assemble(("  ", ""), (sign, style), (f" {where}{event.rel_path}", "")))
    for err in report.errors:
        console.print(Text.assemble((f" {_marks()['fail']} ", "error"), (err, "error")))
    if excludes:
        console.print(f" [dim]Pastas ignoradas (vault.exclude): {escape(', '.join(excludes))}[/dim]")


def highlight(text: str) -> str:
    """Nome de campo ou de vault em destaque, com o texto do usuário escapado."""
    return f"[accent]{escape(text)}[/accent]"


def print_success(message: str) -> None:
    """Resultado de uma ação: `✓` em verde e a mensagem (markup permitido)."""
    console.print(f" [success]{_marks()['ok']}[/success] {message}")


def print_note(message: str) -> None:
    """Complemento em cinza, alinhado com as mensagens de resultado."""
    console.print(f"   [dim]{message}[/dim]")


def print_warning(message: str) -> None:
    console.print(f" [warning]{_marks()['warn']}[/warning] [warning]{escape(message)}[/warning]")


def _config_value(value: object) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def _short(value: object, limit: int = 56) -> str:
    text = _config_value(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


_SOURCE_LABEL = {"env": "ambiente", "db": "settings.db", "default": "padrão"}


def print_config(entries: Sequence[ConfigEntry]) -> None:
    """Campos da configuração, um painel por seção, com a origem de cada valor."""
    print_header("configuração")
    sections: dict[str, list[ConfigEntry]] = {}
    for entry in entries:
        sections.setdefault(entry.section, []).append(entry)
    for section, items in sections.items():
        grid = Table.grid(padding=(0, 3), expand=True)
        grid.add_column(ratio=5)
        grid.add_column(ratio=6)
        for index, entry in enumerate(items):
            origin = _SOURCE_LABEL.get(entry.source, entry.source)
            if entry.source == "env":
                origin += f" · travado por {entry.env_name}"
            elif not entry.editable:
                origin += " · fixo"
            if index:
                grid.add_row("", "")
            left: list[RenderableType] = [Text(entry.key, style="accent")]
            if entry.description:
                left.append(Text(entry.description, style="dim"))
            right = Group(Text(_config_value(entry.value), overflow="fold"), Text(origin, style="dim"))
            grid.add_row(Group(*left), right)
        console.print(_panel(grid, section, expand=True))


def print_history(rows: Sequence[SettingsChange]) -> None:
    """Alterações recentes: número, quando, origem, campo e a troca de valor."""
    print_header("histórico da configuração")
    lines: list[RenderableType] = []
    for index, row in enumerate(rows):
        if index:
            lines.append(Text())
        when = row.changed_at[:16].replace("T", " ")
        lines.append(
            Text.assemble(
                (f"#{row.id}", "accent"),
                ("  ", ""),
                (when, "dim"),
                ("  ", ""),
                (row.source, "dim"),
                ("  ", ""),
                (row.dotted, "bold"),
            )
        )
        change = Text.assemble(
            ("   ", ""),
            (_short(row.old_value), "dim"),
            (" → ", "dim"),
            (_short(row.new_value), ""),
            overflow="fold",
        )
        lines.append(change)
    console.print(_panel(Group(*lines), "Alterações", expand=True))
    console.print(" [dim]Desfazer:[/dim] nix config undo [dim]#id[/dim]")


def print_vaults(rows: Sequence[VaultSettings]) -> None:
    """Vaults cadastrados, com o padrão marcado."""
    print_header("vaults")
    grid = Table.grid(padding=(0, 2))
    grid.add_column(no_wrap=True)
    grid.add_column(no_wrap=True, style="bold")
    grid.add_column(overflow="fold")
    for row in rows:
        mark = Text(_marks()["run"], style="accent") if row.is_default else Text(" ")
        grid.add_row(mark, _cell(row.name), Text(row.path, style="dim"))
    console.print(_panel(grid, "Vaults"))
    console.print(f" [dim]{_marks()['run']} vault padrão[/dim]")


_PLAN_STYLE = {"criar": "success", "alterar": "accent", "sem mudança": "dim"}


def print_plan(project: str, rows: Sequence[tuple[str, str, str]]) -> None:
    """Plano de escrita: o projeto e, por linha, a ação, o arquivo e quem o lê."""
    grid = Table.grid(padding=(0, 2))
    grid.add_column(no_wrap=True)
    grid.add_column(overflow="fold")
    grid.add_column(no_wrap=True, style="dim")
    for action, path, label in rows:
        grid.add_row(Text(action, style=_PLAN_STYLE.get(action, "")), _cell(path), _cell(label))
    console.print(_panel(grid, f"Projeto · {project}"))


def print_table(title: str, columns: Sequence[str], rows: Sequence[Sequence[str]]) -> None:
    """Tabela simples com o mesmo desenho dos painéis."""
    table = Table(
        box=box.ROUNDED,
        header_style="dim",
        border_style="dim",
        padding=(0, 1),
        title=Text(title, style="bold"),
    )
    for column in columns:
        table.add_column(column, overflow="fold")
    for row in rows:
        table.add_row(*(_cell(cell) for cell in row))
    console.print(table)


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
        vault = f"{event.vault} " if event.vault else ""
        description = f"{vault}{event.action} {event.rel_path}"
        completed = event.current
    progress.update(
        task_id,
        total=max(event.total, 1),
        completed=completed,
        description=description,
    )


def print_tokenizer_warning(*, approximate: bool) -> None:
    if approximate:
        console.print(f"[warning]{approximate_tokenizer_hint()}[/warning]")


def print_embedding_choice_table() -> None:
    from nix.cli.embedding_copy import labeled_model_rows

    table = Table(box=box.ROUNDED, header_style="dim", border_style="dim", padding=(0, 1))
    table.add_column("#", style="accent", justify="right")
    table.add_column("Modelo/Raça")
    table.add_column("Disco", no_wrap=True)
    table.add_column("Quando usar")
    for index, (spec, copy) in enumerate(labeled_model_rows(), start=1):
        name = Text(spec.short_name, style="bold")
        if index == 1:
            name.append("  (padrão)", style="accent")
        table.add_row(str(index), Group(name, Text(spec.name, style="dim")), spec.size_label, copy.use_when)
    console.print(table)


def print_step(number: int, total: int, title: str) -> None:
    """Título de uma etapa de um comando interativo; só numera quando há mais de uma."""
    console.print()
    label = f"[accent.strong]{number}/{total}[/accent.strong] " if total > 1 else ""
    console.print(f" {label}[bold]{escape(title)}[/bold]")


def print_problem(message: str) -> None:
    """Problema de entrada num prompt: `✗` em vermelho, com a ação corretiva na mensagem."""
    console.print(f" [error]{_marks()['fail']}[/error] [error]{escape(message)}[/error]")


def print_init_result(result: InitResult) -> None:
    """Resultado do `nix init`: o que foi gravado e o próximo passo."""
    grid = _kv_grid()
    grid.add_row("Configuração", _cell(result.settings_path))
    grid.add_row("Vault", Text.assemble((result.vault_name, "accent"), (f" · {result.vault_path}", "")))
    if result.embedding_written:
        grid.add_row("Embedding", _cell(result.embedding_model))
    print_success("[bold]Configuração concluída.[/bold]")
    console.print(_panel(grid, "Nix"))
    if result.embedding_written and result.previously_initialized:
        print_note("Se o índice já existia com outro modelo, rode `nix sync --full`.")
    console.print(" [dim]Próximo passo:[/dim] nix sync")
