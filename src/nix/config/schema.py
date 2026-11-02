"""Modelos Pydantic da configuração do Nix."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, get_args, get_origin

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator

from nix.config.embedding_models import (
    SUPPORTED_EMBEDDING_MODELS,
    default_embedding_model,
    resolve_embedding_model,
    unsupported_embedding_message,
)
from nix.config.paths import app_root, resolve_app_path, settings_path
from nix.core.errors import ConfigError

LogLevel = Literal["debug", "info", "warning", "error"]
Widget = Literal["bool", "int", "float", "text", "lines", "json", "choice"]

# Primeira wiki sugerido pelo init. A CLI reutiliza esta constante.
DEFAULT_WIKI_NAME = "Default"
MAX_WIKIS = 100
WIKI_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$")
# Pasta de backup usa esse carimbo. Uma wiki com o mesmo formato seria lido como backup.
BACKUP_STAMP_PATTERN = re.compile(r"^\d{8}T\d{6}$")
WIKI_SETTING_KEYS: tuple[str, ...] = (
    "include",
    "exclude",
    "follow_symlinks",
    "default_new_note_folder",
    "default_frontmatter",
    "longterm_folder",
)


def _impact(**flags: bool) -> dict[str, Any]:
    return {"impact": flags}


@dataclass(frozen=True)
class FieldImpact:
    """O que o usuário precisa fazer depois de mudar o campo."""

    requires_full_sync: bool = False
    requires_sync: bool = False
    requires_restart: bool = False
    immutable: bool = False

    def message(self, dotted: str) -> str | None:
        parts: list[str] = []
        if self.requires_full_sync:
            parts.append(f"A mudança em {dotted} só entra no índice com `nix sync --full`.")
        elif self.requires_sync:
            parts.append(f"A mudança em {dotted} só entra no índice com `nix sync`.")
        if self.requires_restart:
            parts.append(
                f"Feche e abra de novo o `nix ui` ou o cliente MCP para {dotted} valer neste processo."
            )
        if not parts:
            return None
        return " ".join(parts)


@dataclass(frozen=True)
class ConfigField:
    section: str
    key: str
    description: str
    default: Any
    annotation: Any
    impact: FieldImpact
    choices: tuple[str, ...] | None
    ge: float | None
    le: float | None

    @property
    def dotted(self) -> str:
        return f"{self.section}.{self.key}"

    @property
    def env_name(self) -> str:
        return f"NIX_{self.section.upper()}__{self.key.upper()}"

    def widget(self) -> Widget:
        if self.choices is not None:
            return "choice"
        annotation = self.annotation
        if annotation is bool:
            return "bool"
        if annotation is int:
            return "int"
        if annotation is float:
            return "float"
        origin = get_origin(annotation)
        if origin is list:
            return "lines"
        if origin is dict:
            return "json"
        return "text"


class AnchoredSettings(BaseModel):
    """Caminhos relativos resolvem contra `path_anchor` (pasta da instalação)."""

    path_anchor: Path | None = Field(default=None, exclude=True)

    def resolve_path(self, value: str) -> Path:
        return resolve_app_path(value, self.path_anchor)


class WikiSettings(AnchoredSettings):
    """Uma wiki nomeada. `include` e os demais ajustes valem só para ela."""

    name: str = Field(
        description="Nome exibido da wiki. A comparação ignora maiúsculas; a grafia original é preservada.",
    )
    is_default: bool = Field(
        default=False,
        description="Wiki usada quando o nome é omitido. Com wikis cadastradas, exatamente uma é a padrão.",
    )
    path: str = Field(
        description="Diretório raiz da wiki. No Windows use barras / (C:/Notas/MinhaWiki).",
    )
    include: list[str] = Field(
        default_factory=lambda: ["**/*.md"],
        description="Padrões de arquivos indexados.",
        json_schema_extra=_impact(requires_sync=True),
    )
    exclude: list[str] = Field(
        default_factory=lambda: [".trash/**", "Templates/**", "Privado/**"],
        description="Padrões ignorados na indexação e na leitura.",
        json_schema_extra=_impact(requires_sync=True),
    )
    follow_symlinks: bool = Field(
        default=False,
        description="Segue links simbólicos dentro da wiki.",
        json_schema_extra=_impact(requires_sync=True),
    )
    default_new_note_folder: str = Field(
        default="Inbox",
        description="Pasta usada quando create_note recebe um caminho sem /.",
    )
    default_frontmatter: dict[str, Any] = Field(
        default_factory=lambda: {"created": "auto", "source": "nix"},
        description='Frontmatter de notas novas. created = "auto" vira a data ISO na criação.',
    )
    longterm_folder: str = Field(
        default="Nix/Memória",
        description="Pasta da ferramenta remember.",
    )
    legacy_layout: bool = Field(
        default=False,
        description=(
            "Definido na migração do esquema 1. O índice e os backups ficam na raiz de "
            "index.data_dir e safety.backup_dir, sem a subpasta do nome."
        ),
    )

    @field_validator("name")
    @classmethod
    def name_is_identifier(cls, value: str) -> str:
        return validate_wiki_name(value)

    @field_validator("path")
    @classmethod
    def path_is_present(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ConfigError(
                "O caminho da wiki está vazio. Informe a pasta com `nix wiki add NOME CAMINHO` "
                "ou rode `nix init`."
            )
        return text

    @property
    def root(self) -> Path:
        return self.resolve_path(self.path)


class IndexSettings(AnchoredSettings):
    data_dir: str = Field(
        default=".nix/data",
        description="Pasta do índice (SQLite e Chroma), relativa à instalação.",
        json_schema_extra=_impact(requires_restart=True, requires_full_sync=True),
    )
    embedding_model: str = Field(
        default_factory=default_embedding_model,
        description="Modelo local de embedding. Trocar exige nix sync --full.",
        json_schema_extra=_impact(requires_full_sync=True, requires_restart=True),
    )
    embedding_batch_size: int = Field(
        default=32,
        ge=1,
        le=256,
        description="Quantos chunks são vetorizados por lote.",
    )
    chunk_size_tokens: int = Field(
        default=800,
        ge=100,
        le=4000,
        description="Tamanho máximo de cada trecho, em tokens.",
        json_schema_extra=_impact(requires_full_sync=True),
    )
    chunk_overlap_tokens: int = Field(
        default=120,
        ge=0,
        le=1000,
        description="Sobreposição entre trechos consecutivos, em tokens.",
        json_schema_extra=_impact(requires_full_sync=True),
    )
    min_chunk_tokens: int = Field(
        default=80,
        ge=0,
        le=500,
        description="Trechos menores que isso são agrupados com o seguinte.",
        json_schema_extra=_impact(requires_full_sync=True),
    )
    auto_sync_external_changes: bool = Field(
        default=False,
        description="Reservado. A v1 rejeita true: o índice só atualiza com nix sync ou sync_index (RN-01).",
        json_schema_extra=_impact(immutable=True),
    )
    auto_index_agent_writes: bool = Field(
        default=True,
        description="Reindexa na hora o que as ferramentas escrevem.",
    )
    warn_when_stale: bool = Field(
        default=True,
        description="Inclui o motivo quando o índice está desatualizado.",
    )
    index_attachments: bool = Field(
        default=True,
        description="Indexa PDFs referenciados pelas notas.",
        json_schema_extra=_impact(requires_sync=True),
    )

    @field_validator("embedding_model")
    @classmethod
    def embedding_supported(cls, value: str) -> str:
        resolved = resolve_embedding_model(value)
        if resolved is None:
            raise ConfigError(unsupported_embedding_message(value))
        return resolved

    @field_validator("auto_sync_external_changes")
    @classmethod
    def no_auto_sync(cls, value: bool) -> bool:
        if value:
            raise ConfigError(
                "index.auto_sync_external_changes=true não é suportado na v1 (RN-01). "
                "Mantenha false e rode `nix sync` ou a ferramenta MCP `sync_index` "
                "quando quiser atualizar o índice."
            )
        return value

    @model_validator(mode="after")
    def overlap_lt_size(self) -> IndexSettings:
        if self.chunk_overlap_tokens >= self.chunk_size_tokens:
            raise ConfigError(
                "index.chunk_overlap_tokens deve ser menor que chunk_size_tokens. "
                "Reduza a sobreposição na configuração."
            )
        return self

    @property
    def data_path(self) -> Path:
        return self.resolve_path(self.data_dir)


class RetrievalSettings(BaseModel):
    top_k: int = Field(default=5, ge=1, le=50, description="Quantos trechos a busca devolve.")
    candidate_pool: int = Field(
        default=20,
        ge=1,
        le=200,
        description="Candidatos avaliados antes do corte.",
    )
    hybrid: bool = Field(default=True, description="Combina busca semântica e léxica.")
    lexical_weight: float = Field(
        default=0.4,
        ge=0.0,
        le=1.0,
        description="Peso da busca léxica no RRF. 0 é só semântica, 1 é só léxica.",
    )
    rrf_k: int = Field(default=60, ge=1, le=200, description="Constante k da fusão RRF.")
    neighbor_expansion: int = Field(
        default=1,
        ge=0,
        le=5,
        description="Trechos vizinhos recuperados em torno de cada resultado.",
    )
    min_score: float = Field(
        default=0.25,
        ge=0.0,
        le=1.0,
        description="Descarta trechos abaixo deste score.",
    )
    expand_query: bool = Field(
        default=True,
        description="Ligado usa OR na busca léxica (mais recall); desligado usa AND (mais precisão).",
    )


class SafetySettings(AnchoredSettings):
    confirm_destructive: bool = Field(
        default=True,
        description="Exige confirmação para sobrescrever ou apagar.",
    )
    backup_before_overwrite: bool = Field(
        default=True,
        description="Grava backup antes de sobrescrever.",
    )
    backup_dir: str = Field(
        default=".nix/backups",
        description="Pasta dos backups, relativa à instalação.",
    )
    backup_retention_days: int = Field(
        default=30,
        ge=1,
        le=365,
        description="Dias até apagar backups antigos.",
    )

    @property
    def backup_path(self) -> Path:
        return self.resolve_path(self.backup_dir)


class LoggingSettings(AnchoredSettings):
    level: LogLevel = Field(default="info", description="Nível do log em arquivo.")
    file: str = Field(
        default=".nix/logs/nix.log",
        description="Caminho do arquivo de log, relativo à instalação.",
    )
    log_prompts: bool = Field(
        default=False,
        description="Inclui consultas e argumentos das ferramentas no log.",
    )

    @property
    def file_path(self) -> Path:
        return self.resolve_path(self.file)


class BrainSettings(BaseModel):
    """Mega Brain. Desligado por padrão. A wiki das páginas conta no limite de 100."""

    enabled: bool = Field(
        default=False,
        description="Liga a captura e as ferramentas brain_.",
        json_schema_extra=_impact(requires_restart=True),
    )
    wiki: str = Field(
        default="",
        description="Wiki das páginas do Mega Brain. Não pode ser removida enquanto estiver ligado.",
    )
    briefing_max_bytes: int = Field(
        default=3000,
        ge=256,
        le=65536,
        description="Teto do perfil no briefing. 6000 quando o projeto ainda não tem memória.",
    )
    idle_end_after_hours: int = Field(
        default=0,
        ge=0,
        le=8760,
        description="Horas sem evento até encerrar a sessão. 0 nunca encerra sozinho.",
    )

    @field_validator("wiki")
    @classmethod
    def wiki_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            return ""
        validate_wiki_name(cleaned)
        return cleaned


class UiSettings(BaseModel):
    """Estado da interface que não entra no formulário nem em `nix config set`.

    `exclude=True` tira o campo de `iter_config_fields` e do `model_dump`.
    `model_validate` continua lendo o valor gravado no settings.db.
    """

    editor_called: bool = Field(
        default=False,
        exclude=True,
        description="O editor já chamou uma ferramenta. Gravado na primeira tools/call.",
    )


class ProfileSettings(BaseModel):
    """Perfil sem modelo de linguagem. A frase mais nova ganha; forget vira lápide."""

    min_projects: int = Field(
        default=2,
        ge=1,
        le=20,
        description="Projetos mínimos com a mesma frase antes de ela entrar no perfil.",
    )


class NixConfig(AnchoredSettings):
    """Configuração validada. Carregada exclusivamente por `nix.config.loader`.

    A lista `wikis` pode estar vazia antes do `nix init`. Com wikis cadastradas,
    vale de 1 a 100, com exatamente um padrão.
    """

    wikis: list[WikiSettings] = Field(default_factory=list)
    index: IndexSettings = Field(default_factory=IndexSettings)
    retrieval: RetrievalSettings = Field(default_factory=RetrievalSettings)
    safety: SafetySettings = Field(default_factory=SafetySettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    brain: BrainSettings = Field(default_factory=BrainSettings)
    profile: ProfileSettings = Field(default_factory=ProfileSettings)
    ui: UiSettings = Field(default_factory=UiSettings)
    settings_path: Path | None = Field(default=None, exclude=True)
    sources: dict[str, str] = Field(default_factory=dict, exclude=True)

    @model_validator(mode="after")
    def apply_path_anchor(self, info: ValidationInfo) -> NixConfig:
        ctx = info.context or {}
        raw = ctx.get("path_anchor")
        if isinstance(raw, Path):
            anchor = raw
        elif self.path_anchor is not None:
            anchor = self.path_anchor
        else:
            anchor = app_root()
        self.path_anchor = anchor
        for wiki in self.wikis:
            wiki.path_anchor = anchor
        self.index.path_anchor = anchor
        self.safety.path_anchor = anchor
        self.logging.path_anchor = anchor
        validate_wiki_collection(self.wikis)
        return self

    @property
    def default_wiki(self) -> WikiSettings:
        """Wiki usada quando o nome é omitido."""
        if not self.wikis:
            raise ConfigError(
                f"Nenhuma wiki configurada ({settings_path()}). Rode `nix init` para cadastrar a primeira."
            )
        for wiki in self.wikis:
            if wiki.is_default:
                return wiki
        raise ConfigError("Nenhuma wiki está marcado como padrão. Use `nix wiki default NOME`.")

    def get_wiki(self, name: str) -> WikiSettings:
        """Acha a wiki pelo nome, sem diferenciar maiúsculas."""
        folded = name.strip().casefold()
        for wiki in self.wikis:
            if wiki.name.casefold() == folded:
                return wiki
        raise ConfigError(unknown_wiki_message(name, [(wiki.name, wiki.is_default) for wiki in self.wikis]))

    def require_wiki(self, name: str | None = None) -> Path:
        """Garante que a wiki pedido (ou o padrão) existe e é um diretório."""
        if not self.wikis:
            raise ConfigError(
                f"Nenhuma wiki configurada ({settings_path()}). Rode `nix init` para cadastrar a primeira."
            )
        wiki = self.default_wiki if name is None else self.get_wiki(name)
        root = wiki.root
        if not root.exists():
            shown = root.as_posix()
            raise ConfigError(
                f"A wiki {wiki.name} aponta para {shown}, que não existe. "
                f"Crie a pasta (mkdir \"{shown}\") ou ajuste o caminho com `nix wiki`."
            )
        if not root.is_dir():
            raise ConfigError(
                f"A wiki {wiki.name} aponta para {root.as_posix()}, que não é um diretório. "
                "Aponte para a pasta da wiki com `nix wiki`."
            )
        return root

    def _named_vault(self, wiki: WikiSettings | None) -> WikiSettings:
        if wiki is not None:
            return wiki
        return self.default_wiki

    def wiki_index_dir(self, wiki: WikiSettings | None = None) -> Path:
        """Índice da wiki: `{index.data_dir}/{nome}`.

        A wiki migrada do esquema 1 (`legacy_layout`) continua na raiz de
        `index.data_dir`, onde já estavam `index.db` e o chroma.
        """
        chosen = self._named_vault(wiki)
        if chosen.legacy_layout:
            return self.index.data_path
        return self.index.data_path / chosen.name

    def wiki_backup_dir(self, wiki: WikiSettings | None = None) -> Path:
        """Backups da wiki: `{safety.backup_dir}/{nome}`. A base continua global.

        A wiki migrada do esquema 1 usa a raiz de `safety.backup_dir`.
        """
        chosen = self._named_vault(wiki)
        if chosen.legacy_layout:
            return self.safety.backup_path
        return self.safety.backup_path / chosen.name

    def wiki_sync_lock_path(self, wiki: WikiSettings | None = None) -> Path:
        """Trava da wiki: `{app_root}/.nix/sync-{nome}.lock`."""
        chosen = self._named_vault(wiki)
        anchor = self.path_anchor or app_root()
        return anchor / ".nix" / f"sync-{chosen.name}.lock"


_SECTION_MODELS: tuple[tuple[str, type[BaseModel]], ...] = (
    ("index", IndexSettings),
    ("retrieval", RetrievalSettings),
    ("safety", SafetySettings),
    ("logging", LoggingSettings),
    ("brain", BrainSettings),
    ("profile", ProfileSettings),
    ("ui", UiSettings),
)


def validate_wiki_name(name: str) -> str:
    """Aceita o identificador e devolve a grafia original, sem espaços nas pontas."""
    cleaned = name.strip()
    if WIKI_NAME_PATTERN.fullmatch(cleaned) is None:
        raise ConfigError(
            f"Nome de wiki {name!r} inválido. Use de 1 a 32 caracteres, começando com letra ou dígito, "
            "e depois apenas letras, dígitos, _ ou -. Exemplo: Default."
        )
    if BACKUP_STAMP_PATTERN.fullmatch(cleaned):
        raise ConfigError(
            f"Nome de wiki {cleaned!r} tem o formato de um carimbo de backup (AAAAMMDDTHHMMSS). "
            "Escolha outro nome, por exemplo Trabalho."
        )
    return cleaned


def unknown_wiki_message(name: str, wikis: list[tuple[str, bool]]) -> str:
    known = ", ".join(item[0] for item in wikis) or "(nenhum)"
    default = next((item[0] for item in wikis if item[1]), None)
    hint = f" O padrão é {default}." if default else ""
    return (
        f"Wiki {name!r} não existe. Wikis cadastradas: {known}.{hint} "
        "Veja os nomes com `nix wiki list`."
    )


def wiki_paths_overlap(left: Path, right: Path) -> bool:
    """True se os caminhos resolvidos são o mesmo ou um está dentro do outro."""
    a = os.path.normcase(str(left.resolve()))
    b = os.path.normcase(str(right.resolve()))
    if a == b:
        return True
    sep = os.sep
    a_prefix = a.rstrip(sep) + sep
    b_prefix = b.rstrip(sep) + sep
    return a.startswith(b_prefix) or b.startswith(a_prefix)


def validate_wiki_collection(wikis: list[WikiSettings]) -> None:
    """Regras do conjunto. Lista vazia é o estado anterior ao init."""
    if not wikis:
        return
    if len(wikis) > MAX_WIKIS:
        raise ConfigError(
            f"O Nix aceita no máximo {MAX_WIKIS} wikis e encontrou {len(wikis)}. "
            "Remova um com `nix wiki remove NOME`."
        )
    defaults = [wiki.name for wiki in wikis if wiki.is_default]
    if len(defaults) != 1:
        raise ConfigError(
            "É preciso haver exatamente uma wiki padrão. Escolha com `nix wiki default NOME`."
        )
    seen: dict[str, str] = {}
    for wiki in wikis:
        folded = wiki.name.casefold()
        previous = seen.get(folded)
        if previous is not None:
            raise ConfigError(
                f"Os nomes {previous!r} e {wiki.name!r} coincidem (a comparação ignora maiúsculas). "
                "Renomeie um com `nix wiki rename ANTIGO NOVO`."
            )
        seen[folded] = wiki.name
    for index, left in enumerate(wikis):
        for right in wikis[index + 1 :]:
            if wiki_paths_overlap(left.root, right.root):
                raise ConfigError(
                    f"As wikis {left.name!r} ({left.path}) e {right.name!r} ({right.path}) "
                    "têm caminhos iguais ou um dentro do outro. "
                    "Separe as pastas com `nix wiki`."
                )


def default_wiki_settings() -> dict[str, Any]:
    """Ajustes iniciais gravados em `wikis.settings_json`."""
    found: dict[str, Any] = {}
    for key in WIKI_SETTING_KEYS:
        field = WikiSettings.model_fields[key]
        value = field.get_default(call_default_factory=True)
        if isinstance(value, list):
            value = list(value)
        elif isinstance(value, dict):
            value = dict(value)
        found[key] = value
    return found


def _impact_of(field: Any) -> FieldImpact:
    extra = getattr(field, "json_schema_extra", None)
    raw: dict[str, Any] = {}
    if isinstance(extra, dict):
        impact = extra.get("impact")
        if isinstance(impact, dict):
            raw = impact
    return FieldImpact(
        requires_full_sync=bool(raw.get("requires_full_sync")),
        requires_sync=bool(raw.get("requires_sync")),
        requires_restart=bool(raw.get("requires_restart")),
        immutable=bool(raw.get("immutable")),
    )


def _bounds(field: Any) -> tuple[float | None, float | None]:
    lower: float | None = None
    upper: float | None = None
    metadata = getattr(field, "metadata", ())
    for meta in metadata:
        kind = type(meta).__name__
        if kind == "Ge":
            raw_ge = getattr(meta, "ge", None)
            if isinstance(raw_ge, int | float) and not isinstance(raw_ge, bool):
                lower = float(raw_ge)
        elif kind == "Le":
            raw_le = getattr(meta, "le", None)
            if isinstance(raw_le, int | float) and not isinstance(raw_le, bool):
                upper = float(raw_le)
    return lower, upper


def _choices(section: str, key: str, annotation: Any) -> tuple[str, ...] | None:
    if section == "index" and key == "embedding_model":
        return SUPPORTED_EMBEDDING_MODELS
    if get_origin(annotation) is Literal:
        return tuple(str(item) for item in get_args(annotation))
    return None


def excluded_setting_keys() -> tuple[tuple[str, str], ...]:
    """Campos de seção com `exclude=True`, fora `path_anchor`.

    Hoje só `ui.editor_called`. Ficam no settings.db e fora do histórico.
    """
    found: list[tuple[str, str]] = []
    for section, model in _SECTION_MODELS:
        for name, field in model.model_fields.items():
            if name == "path_anchor" or not field.exclude:
                continue
            found.append((section, name))
    return tuple(found)


def iter_config_fields(*, include_excluded: bool = False) -> list[ConfigField]:
    """Campos graváveis, na ordem das seções.

    `include_excluded` alcança campos com `exclude=True` (a marca `ui.editor_called`).
    O formulário e o `nix config set` usam o padrão e não os veem. `path_anchor` nunca entra.
    """
    found: list[ConfigField] = []
    for section, model in _SECTION_MODELS:
        for name, field in model.model_fields.items():
            if name == "path_anchor":
                continue
            if field.exclude and not include_excluded:
                continue
            lower, upper = _bounds(field)
            found.append(
                ConfigField(
                    section=section,
                    key=name,
                    description=field.description or "",
                    default=field.get_default(call_default_factory=True),
                    annotation=field.annotation,
                    impact=_impact_of(field),
                    choices=_choices(section, name, field.annotation),
                    ge=lower,
                    le=upper,
                )
            )
    return found


def config_field(section: str, key: str, *, include_excluded: bool = False) -> ConfigField:
    for field in iter_config_fields(include_excluded=include_excluded):
        if field.section == section and field.key == key:
            return field
    raise KeyError(section, key)
