"""Ferramentas MCP do Mega Brain. Só aparecem com `brain.enabled`."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from nix.core.brain.paths import CURATED_DIRS, PROFILE_CATEGORIES, is_curated_or_profile
from nix.core.brain.query import brain_query as run_query
from nix.core.brain.query import brain_runtime
from nix.core.brain.store import BrainStore
from nix.core.errors import ConfigError, WikiError
from nix.core.runtime import RuntimeHost

_PAGE_HINT = (
    "Grave em projects/<projeto>/_rules|decisions|gotchas|procedures|concepts/ "
    f"ou em profile/{'|'.join(PROFILE_CATEGORIES)}/."
)


def _require_enabled(host: RuntimeHost) -> None:
    if not host.config.brain.enabled:
        raise ConfigError(
            "O Mega Brain está desligado. Rode `nix brain enable --wiki NOME` e reinicie o cliente MCP."
        )


class BrainQueryArgs(BaseModel):
    query: str
    project: str = ""
    scope: Literal["project", "global"] = "project"
    path_prefix: str = ""
    tag: str = ""
    kind: str = ""


def brain_query(host: RuntimeHost, args: BrainQueryArgs) -> dict[str, object]:
    _require_enabled(host)
    return run_query(
        host,
        query=args.query,
        project=args.project,
        scope=args.scope,
        path_prefix=args.path_prefix,
        tag=args.tag,
        kind=args.kind,
    )


class BrainStatusArgs(BaseModel):
    project: str = ""


def brain_status(host: RuntimeHost, args: BrainStatusArgs) -> dict[str, object]:
    _require_enabled(host)
    store = BrainStore()
    from nix.core.brain.events import find_project

    project = args.project.strip() or find_project("")[0]
    sessions = store.sessions_for(project)
    return {
        "enabled": True,
        "wiki": host.config.brain.wiki,
        "project": project,
        "sessions": len(sessions),
        "open_sessions": sum(1 for row in sessions if row.status == "open"),
    }


class BrainReadPageArgs(BaseModel):
    path: str


def brain_read_page(host: RuntimeHost, args: BrainReadPageArgs) -> dict[str, object]:
    _require_enabled(host)
    runtime = brain_runtime(host)
    text = runtime.reader.read_text(args.path)
    return {"wiki": runtime.wiki.name, "path": args.path, "content": text}


class BrainRecentPagesArgs(BaseModel):
    project: str = ""
    limit: int = Field(default=10, ge=1, le=50)


def brain_recent_pages(host: RuntimeHost, args: BrainRecentPagesArgs) -> dict[str, object]:
    _require_enabled(host)
    store = BrainStore()
    project_key = args.project.strip() or None
    rows = store.recent_pages(project_key, args.limit)
    return {
        "pages": [
            {
                "path": row.page_path,
                "project": row.project_name,
                "agent": row.agent,
                "started_at": row.started_at,
            }
            for row in rows
        ]
    }


class BrainWritePageArgs(BaseModel):
    path: str
    content: str
    confirm: bool = False


def brain_write_page(host: RuntimeHost, args: BrainWritePageArgs) -> dict[str, object]:
    _require_enabled(host)
    _require_curated(args.path)
    runtime = brain_runtime(host)
    result = runtime.writer.create_note(args.path, args.content, overwrite=True, confirm=args.confirm)
    written = runtime.writeback.after_write(result)
    return {"wiki": runtime.wiki.name, "path": written.rel_path, "action": written.action}


class BrainPatchPageArgs(BaseModel):
    path: str
    old: str
    new: str
    confirm: bool = False


def brain_patch_page(host: RuntimeHost, args: BrainPatchPageArgs) -> dict[str, object]:
    _require_enabled(host)
    _require_curated(args.path)
    if not args.old:
        raise ConfigError("Informe o trecho antigo em `old`. A troca é literal.")
    runtime = brain_runtime(host)
    current = runtime.reader.read_text(args.path, keep_newlines=True)
    if args.old not in current:
        raise WikiError(
            f"O trecho não está em {args.path}. Leia a página com brain_read_page e copie o texto exato."
        )
    updated = current.replace(args.old, args.new, 1)
    result = runtime.writer.update_note(args.path, updated, mode="replace", confirm=args.confirm)
    written = runtime.writeback.after_write(result)
    return {"wiki": runtime.wiki.name, "path": written.rel_path, "action": written.action}


class BrainDeletePageArgs(BaseModel):
    path: str
    confirm: bool = False


def brain_delete_page(host: RuntimeHost, args: BrainDeletePageArgs) -> dict[str, object]:
    _require_enabled(host)
    _require_curated(args.path)
    runtime = brain_runtime(host)
    result = runtime.writer.delete_note(args.path, confirm=args.confirm)
    written = runtime.writeback.after_write(result)
    return {"wiki": runtime.wiki.name, "path": written.rel_path, "action": written.action}


class BrainFeedbackArgs(BaseModel):
    path: str
    useful: bool
    note: str = ""
    project: str = ""


def brain_feedback(host: RuntimeHost, args: BrainFeedbackArgs) -> dict[str, object]:
    _require_enabled(host)
    BrainStore().add_feedback(args.path, args.project.strip(), args.useful, args.note.strip())
    return {"path": args.path, "useful": args.useful}


class BrainReadSessionObservationsArgs(BaseModel):
    session: str


def brain_read_session_observations(host: RuntimeHost, args: BrainReadSessionObservationsArgs) -> dict[str, object]:
    _require_enabled(host)
    rows = BrainStore().observations(args.session.strip())
    if not rows:
        raise ConfigError(
            f"Não há observações da sessão {args.session!r}. "
            "Use brain_recent_pages para achar a página e o projeto."
        )
    return {
        "session": args.session,
        "observations": [
            {
                "id": row.id,
                "kind": row.kind,
                "ts": row.ts,
                "tool": row.tool,
                "target": row.target,
                "text": row.text,
                "is_error": row.is_error,
            }
            for row in rows
        ],
    }


class BrainBriefingArgs(BaseModel):
    project: str = ""
    session: str = ""
    agent: str = ""


def brain_briefing(host: RuntimeHost, args: BrainBriefingArgs) -> dict[str, object]:
    _require_enabled(host)
    from nix.core.brain.briefing import build_briefing

    project = _project_key(args.project)
    text = build_briefing(project, current_session=args.session.strip(), agent=args.agent.strip())
    return {"project": project, "text": text}


class BrainHandoffCreateArgs(BaseModel):
    text: str
    project: str = ""
    session: str = ""


def brain_handoff_create(host: RuntimeHost, args: BrainHandoffCreateArgs) -> dict[str, object]:
    _require_enabled(host)
    from nix.core.brain.handoff import create

    project = _project_key(args.project)
    row = create(project, args.text, args.session.strip())
    return {"project": project, "id": row.id, "status": row.status, "text": row.body}


class BrainHandoffListArgs(BaseModel):
    project: str = ""


def brain_handoff_list(host: RuntimeHost, args: BrainHandoffListArgs) -> dict[str, object]:
    _require_enabled(host)
    from nix.core.brain.handoff import listed

    project = _project_key(args.project)
    return {"project": project, "handoffs": listed(project)}


class BrainHandoffAcceptArgs(BaseModel):
    agent: str
    project: str = ""


def brain_handoff_accept(host: RuntimeHost, args: BrainHandoffAcceptArgs) -> dict[str, object]:
    _require_enabled(host)
    from nix.core.brain.handoff import accept

    project = _project_key(args.project)
    result = accept(project, args.agent)
    result["project"] = project
    return result


class BrainHandoffCancelArgs(BaseModel):
    project: str = ""


def brain_handoff_cancel(host: RuntimeHost, args: BrainHandoffCancelArgs) -> dict[str, object]:
    _require_enabled(host)
    from nix.core.brain.handoff import cancel

    return cancel(_project_key(args.project))


class BrainMessageSendArgs(BaseModel):
    text: str
    project: str = ""
    recipient: str = ""


def brain_message_send(host: RuntimeHost, args: BrainMessageSendArgs) -> dict[str, object]:
    _require_enabled(host)
    from nix.core.brain.inbox import send

    return send(_project_key(args.project), args.text, args.recipient)


class BrainMessageListArgs(BaseModel):
    project: str = ""


def brain_message_list(host: RuntimeHost, args: BrainMessageListArgs) -> dict[str, object]:
    _require_enabled(host)
    from nix.core.brain.inbox import listed

    project = _project_key(args.project)
    return {"project": project, "messages": listed(project)}


class BrainMessagePopArgs(BaseModel):
    project: str = ""
    agent: str = ""


def brain_message_pop(host: RuntimeHost, args: BrainMessagePopArgs) -> dict[str, object]:
    _require_enabled(host)
    from nix.core.brain.inbox import pop

    result = pop(_project_key(args.project), args.agent)
    result["project"] = _project_key(args.project)
    return result


class BrainMessageCancelArgs(BaseModel):
    id: int


def brain_message_cancel(host: RuntimeHost, args: BrainMessageCancelArgs) -> dict[str, object]:
    _require_enabled(host)
    from nix.core.brain.inbox import cancel

    return cancel(args.id)


def _project_key(raw: str) -> str:
    from nix.core.brain.events import find_project

    return find_project(raw.strip())[0]


def _require_curated(path: str) -> None:
    if is_curated_or_profile(path):
        return
    folders = ", ".join(CURATED_DIRS)
    raise ConfigError(
        f"O caminho {path!r} não é uma página curada nem de perfil. {_PAGE_HINT} Pastas: {folders}."
    )
