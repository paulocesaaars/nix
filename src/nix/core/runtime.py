"""Composição do núcleo: store, vault, recuperação e indexação."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from nix.config.schema import NixConfig
from nix.core.index.embedder import Embedder
from nix.core.index.graph import WikiGraph
from nix.core.index.staleness import compute_status
from nix.core.index.store import IndexStore
from nix.core.index.sync import Indexer
from nix.core.index.vectorstore import VectorStore
from nix.core.index.writeback import Writeback
from nix.core.models import IndexStatus
from nix.core.retrieval.service import RetrievalService
from nix.core.vault.reader import VaultReader
from nix.core.vault.writer import VaultWriter
from nix.observability.logging import configure_logging, get_logger


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

    @classmethod
    def from_config(cls, config: NixConfig) -> Runtime:
        configure_logging(config)
        log = get_logger("nix.config")
        for warning in config.legacy_warnings:
            log.warning("%s", warning)
        config.require_vault()
        data_dir: Path = config.index.data_path
        data_dir.mkdir(parents=True, exist_ok=True)
        store = IndexStore(data_dir / "index.db")
        vectors = VectorStore(data_dir / "chroma")
        embedder = Embedder(config.index.embedding_model, config.index.embedding_batch_size)
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
