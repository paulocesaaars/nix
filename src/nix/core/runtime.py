"""Composição do núcleo: store, vault, recuperação e indexação."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from nix.config.schema import NixConfig
from nix.core.index.embedder import Embedder
from nix.core.index.graph import WikiGraph
from nix.core.index.native_compat import prepare_native_imports
from nix.core.index.staleness import compute_status
from nix.core.index.store import IndexStore
from nix.core.index.sync import Indexer
from nix.core.index.vectorstore import VectorStore
from nix.core.index.writeback import Writeback
from nix.core.models import IndexStatus
from nix.core.retrieval.service import RetrievalService
from nix.core.vault.reader import VaultReader
from nix.core.vault.writer import VaultWriter
from nix.observability.logging import configure_logging


@dataclass
class Runtime:
    config: NixConfig
    store: IndexStore
    vectors: VectorStore
    embedder: Embedder
    reader: VaultReader
    writer: VaultWriter
    indexer: Indexer
    writeback: Writeback
    retrieval: RetrievalService
    graph: WikiGraph
    capture_embedder_stdout: bool = True

    @classmethod
    def from_config(
        cls,
        config: NixConfig,
        *,
        capture_embedder_stdout: bool = True,
    ) -> Runtime:
        configure_logging(config)
        config.require_vault()
        prepare_native_imports()
        data_dir: Path = config.index.data_path
        data_dir.mkdir(parents=True, exist_ok=True)
        store = IndexStore(data_dir / "index.db")
        vectors = VectorStore(data_dir / "chroma")
        embedder = Embedder(
            config.index.embedding_model,
            config.index.embedding_batch_size,
            capture_stdout=capture_embedder_stdout,
        )
        reader = VaultReader(config)
        writer = VaultWriter(config, reader)
        graph = WikiGraph(store)
        indexer = Indexer(config, store, vectors, embedder, reader, on_change=graph.invalidate)
        writeback = Writeback(indexer)
        retrieval = RetrievalService(config, store, vectors, embedder)
        return cls(
            config=config,
            store=store,
            vectors=vectors,
            embedder=embedder,
            reader=reader,
            writer=writer,
            indexer=indexer,
            writeback=writeback,
            retrieval=retrieval,
            graph=graph,
            capture_embedder_stdout=capture_embedder_stdout,
        )

    def status(self) -> IndexStatus:
        return compute_status(
            self.store,
            self.reader,
            data_dir=str(self.config.index.data_path),
            warn_when_stale=self.config.index.warn_when_stale,
        )

    def close(self) -> None:
        self.store.close()
        self.vectors.close()


class RuntimeHost:
    """Runtime do processo, recarregado quando o settings.db muda.

    `embedding_model` e `data_dir` ficam os do processo vivo. O restante da
    configuração entra na chamada seguinte, e o aviso continua enquanto os dois
    campos presos ainda divergirem.
    """

    def __init__(self, runtime: Runtime) -> None:
        from nix.config.store import SettingsStore

        self.runtime = runtime
        self._stamp = SettingsStore().updated_at()
        self._restart_notice: str | None = None

    def before_call(self) -> str | None:
        from nix.config.loader import clear_config_cache, load_config
        from nix.config.store import SettingsStore
        from nix.core.errors import NixError

        stamp = SettingsStore().updated_at()
        if stamp == self._stamp:
            return self._restart_notice
        clear_config_cache()
        try:
            new_config = load_config(use_cache=False)
        except NixError as exc:
            return exc.message
        notice = _restart_notice(self.runtime.config, new_config)
        pinned = _pin_live_index(self.runtime.config, new_config)
        if _same_settings(pinned, self.runtime.config):
            self._stamp = stamp
            self._restart_notice = notice
            return notice
        try:
            fresh = Runtime.from_config(
                pinned,
                capture_embedder_stdout=self.runtime.capture_embedder_stdout,
            )
        except NixError as exc:
            return exc.message
        old = self.runtime
        self.runtime = fresh
        old.close()
        self._stamp = stamp
        self._restart_notice = notice
        return notice

    def close(self) -> None:
        self.runtime.close()


def _restart_notice(current: NixConfig, new_config: NixConfig) -> str | None:
    blocked: list[str] = []
    if new_config.index.embedding_model != current.index.embedding_model:
        blocked.append("index.embedding_model")
    if new_config.index.data_path != current.index.data_path:
        blocked.append("index.data_dir")
    if not blocked:
        return None
    joined = " e ".join(blocked)
    return (
        f"{joined} mudou, mas este processo ainda usa o valor anterior. "
        "Feche e abra de novo o `nix ui` ou o cliente MCP. "
        "Se o modelo de embedding mudou, rode `nix sync --full`."
    )


def _pin_live_index(current: NixConfig, new_config: NixConfig) -> NixConfig:
    index = new_config.index.model_copy(
        update={
            "embedding_model": current.index.embedding_model,
            "data_dir": current.index.data_dir,
        }
    )
    return new_config.model_copy(update={"index": index})


def _same_settings(left: NixConfig, right: NixConfig) -> bool:
    return left.model_dump(mode="json") == right.model_dump(mode="json")

