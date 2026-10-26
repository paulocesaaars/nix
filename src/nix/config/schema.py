"""Modelos Pydantic da configuração do Nix."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, get_args, get_origin

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator

from nix.config.embedding_models import SUPPORTED_EMBEDDING_MODELS, default_embedding_model
from nix.config.paths import app_root, resolve_app_path, settings_path
from nix.core.errors import ConfigError

SUPPORTED_RERANK_MODELS: tuple[str, ...] = (
    "Xenova/ms-marco-MiniLM-L-6-v2",
    "Xenova/ms-marco-MiniLM-L-12-v2",
)

LogLevel = Literal["debug", "info", "warning", "error"]
Widget = Literal["bool", "int", "float", "text", "lines", "json", "choice"]


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


class VaultSettings(AnchoredSettings):
    path: str = Field(
        default="",
        description="Diretório raiz do vault do Obsidian. No Windows use barras / (C:/Obsidian/MeuVault).",
        json_schema_extra=_impact(requires_sync=True),
    )
    include: list[str] = Field(
        default_factory=lambda: ["**/*.md"],
        description="Padrões de arquivos indexados.",
        json_schema_extra=_impact(requires_sync=True),
    )
    exclude: list[str] = Field(
        default_factory=lambda: [".obsidian/**", ".trash/**", "Templates/**", "Privado/**"],
        description="Padrões ignorados na indexação e na leitura.",
        json_schema_extra=_impact(requires_sync=True),
    )
    follow_symlinks: bool = Field(
        default=False,
        description="Segue links simbólicos dentro do vault.",
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
    rerank_model: str = Field(
        default="Xenova/ms-marco-MiniLM-L-6-v2",
        description="Cross-encoder local, usado só se retrieval.rerank estiver ligado.",
    )

    @field_validator("embedding_model")
    @classmethod
    def embedding_supported(cls, value: str) -> str:
        if value not in SUPPORTED_EMBEDDING_MODELS:
            allowed = ", ".join(SUPPORTED_EMBEDDING_MODELS)
            raise ConfigError(
                f"index.embedding_model={value!r} não é suportado. Use um de: {allowed}. Depois rode `nix sync --full`."
            )
        return value

    @field_validator("rerank_model")
    @classmethod
    def rerank_supported(cls, value: str) -> str:
        if value not in SUPPORTED_RERANK_MODELS:
            allowed = ", ".join(SUPPORTED_RERANK_MODELS)
            raise ConfigError(f"index.rerank_model={value!r} não é suportado. Use um de: {allowed}.")
        return value

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
    rerank: bool = Field(
        default=False,
        description="Reordena os melhores resultados com o cross-encoder local.",
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


class NixConfig(AnchoredSettings):
    """Configuração validada. Carregada exclusivamente por `nix.config.loader`."""

    vault: VaultSettings = Field(default_factory=VaultSettings)
    index: IndexSettings = Field(default_factory=IndexSettings)
    retrieval: RetrievalSettings = Field(default_factory=RetrievalSettings)
    safety: SafetySettings = Field(default_factory=SafetySettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
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
        self.vault.path_anchor = anchor
        self.index.path_anchor = anchor
        self.safety.path_anchor = anchor
        self.logging.path_anchor = anchor
        return self

    def require_vault(self) -> Path:
        if not self.vault.path.strip():
            raise ConfigError(
                "vault.path não está definido. Rode `nix init` para apontar o vault "
                f"({settings_path()})."
            )
        root = self.vault.root
        if not root.exists():
            raise ConfigError(
                f"O vault {root} não existe. Crie o diretório ou rode `nix init --vault CAMINHO`."
            )
        if not root.is_dir():
            raise ConfigError(f"vault.path={root} não é um diretório. Aponte para a pasta do vault do Obsidian.")
        return root


_SECTION_MODELS: tuple[tuple[str, type[BaseModel]], ...] = (
    ("vault", VaultSettings),
    ("index", IndexSettings),
    ("retrieval", RetrievalSettings),
    ("safety", SafetySettings),
    ("logging", LoggingSettings),
)


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
    if section == "index" and key == "rerank_model":
        return SUPPORTED_RERANK_MODELS
    if get_origin(annotation) is Literal:
        return tuple(str(item) for item in get_args(annotation))
    return None


def iter_config_fields() -> list[ConfigField]:
    """Campos graváveis, na ordem das seções."""
    found: list[ConfigField] = []
    for section, model in _SECTION_MODELS:
        for name, field in model.model_fields.items():
            if field.exclude or name == "path_anchor":
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


def config_field(section: str, key: str) -> ConfigField:
    for field in iter_config_fields():
        if field.section == section and field.key == key:
            return field
    raise KeyError(section, key)
