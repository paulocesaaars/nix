"""Modelos Pydantic da configuração do Nix."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator

from nix.config.embedding_models import SUPPORTED_EMBEDDING_MODELS, default_embedding_model
from nix.config.paths import app_root, resolve_app_path
from nix.core.errors import ConfigError

SUPPORTED_RERANK_MODELS: tuple[str, ...] = (
    "Xenova/ms-marco-MiniLM-L-6-v2",
    "Xenova/ms-marco-MiniLM-L-12-v2",
)

LogLevel = Literal["debug", "info", "warning", "error"]


class AnchoredSettings(BaseModel):
    """Caminhos relativos resolvem contra `path_anchor` (diretório do TOML)."""

    path_anchor: Path | None = Field(default=None, exclude=True)

    def resolve_path(self, value: str) -> Path:
        return resolve_app_path(value, self.path_anchor)


class VaultSettings(AnchoredSettings):
    path: str = ""
    include: list[str] = Field(default_factory=lambda: ["**/*.md"])
    exclude: list[str] = Field(default_factory=lambda: [".obsidian/**", ".trash/**", "Templates/**", "Privado/**"])
    follow_symlinks: bool = False
    default_new_note_folder: str = "Inbox"
    default_frontmatter: dict[str, Any] = Field(default_factory=lambda: {"created": "auto", "source": "nix"})
    longterm_folder: str = "Nix/Memória"

    @property
    def root(self) -> Path:
        return self.resolve_path(self.path)


class IndexSettings(AnchoredSettings):
    data_dir: str = ".nix/data"
    embedding_model: str = default_embedding_model()
    embedding_batch_size: int = Field(default=32, ge=1, le=256)
    chunk_size_tokens: int = Field(default=800, ge=100, le=4000)
    chunk_overlap_tokens: int = Field(default=120, ge=0, le=1000)
    min_chunk_tokens: int = Field(default=80, ge=0, le=500)
    auto_sync_external_changes: bool = False
    auto_index_agent_writes: bool = True
    warn_when_stale: bool = True
    index_attachments: bool = True
    rerank_model: str = "Xenova/ms-marco-MiniLM-L-6-v2"

    @field_validator("embedding_model")
    @classmethod
    def embedding_supported(cls, value: str) -> str:
        if value not in SUPPORTED_EMBEDDING_MODELS:
            allowed = ", ".join(SUPPORTED_EMBEDDING_MODELS)
            raise ConfigError(
                f"index.embedding_model={value!r} não é suportado. Use um de: {allowed}. Depois rode `nix sync --full`."
            )
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
                "Reduza a sobreposição no arquivo de configuração."
            )
        return self

    @property
    def data_path(self) -> Path:
        return self.resolve_path(self.data_dir)


class RetrievalSettings(BaseModel):
    top_k: int = Field(default=5, ge=1, le=50)
    candidate_pool: int = Field(default=20, ge=1, le=200)
    hybrid: bool = True
    lexical_weight: float = Field(default=0.4, ge=0.0, le=1.0)
    rrf_k: int = Field(default=60, ge=1, le=200)
    neighbor_expansion: int = Field(default=1, ge=0, le=5)
    min_score: float = Field(default=0.25, ge=0.0, le=1.0)
    rerank: bool = False
    expand_query: bool = True


class SafetySettings(AnchoredSettings):
    confirm_destructive: bool = True
    backup_before_overwrite: bool = True
    backup_dir: str = ".nix/backups"
    backup_retention_days: int = Field(default=30, ge=1, le=365)

    @property
    def backup_path(self) -> Path:
        return self.resolve_path(self.backup_dir)


class LoggingSettings(AnchoredSettings):
    level: LogLevel = "info"
    file: str = ".nix/logs/nix.log"
    log_prompts: bool = False

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
    config_path: Path | None = Field(default=None, exclude=True)
    unknown_sections: list[str] = Field(default_factory=list, exclude=True)
    legacy_warnings: list[str] = Field(default_factory=list, exclude=True)

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
            if self.config_path is None:
                raise ConfigError(
                    "Não há arquivo de configuração e vault.path está vazio. "
                    "Rode `nix init` para criar nix.toml na pasta do Nix, "
                    "defina vault.path e depois `nix doctor`."
                )
            raise ConfigError(
                "vault.path não está definido. Edite o arquivo de configuração "
                f"({self.config_path}) e aponte para o diretório do vault, "
                "depois rode `nix doctor`."
            )
        root = self.vault.root
        if not root.exists():
            raise ConfigError(
                f"O vault {root} não existe. Crie o diretório ou corrija vault.path no arquivo de configuração."
            )
        if not root.is_dir():
            raise ConfigError(f"vault.path={root} não é um diretório. Aponte para a pasta do vault do Obsidian.")
        return root
