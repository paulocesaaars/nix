"""Composição do núcleo: um runtime por wiki e um Embedder compartilhado."""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass

from nix.config.schema import NixConfig, WikiSettings
from nix.core.errors import ConfigError, NixError
from nix.core.index.embedder import Embedder
from nix.core.index.graph import WikiGraph
from nix.core.index.lock import add_sync_idle_listener, remove_sync_idle_listener, sync_in_progress
from nix.core.index.native_compat import prepare_native_imports
from nix.core.index.staleness import compute_status
from nix.core.index.store import IndexStore
from nix.core.index.sync import Indexer
from nix.core.index.vectorstore import VectorStore
from nix.core.index.writeback import Writeback
from nix.core.models import IndexStatus
from nix.core.retrieval.service import RetrievalService
from nix.core.wiki.reader import WikiReader
from nix.core.wiki.writer import WikiWriter
from nix.observability.logging import configure_logging

WikiSpec = str | list[str] | None


@dataclass(frozen=True)
class WikiOpenError:
    """Falha ao abrir uma wiki que já está cadastrado. O nome existe; a pasta ou o índice não."""

    name: str
    message: str
    path: str
    is_default: bool


@dataclass(frozen=True)
class OpenedWikis:
    """Runtimes abertos e as falhas isoladas dos demais nomes do mesmo pedido."""

    runtimes: list[Runtime]
    errors: list[WikiOpenError]


_SINGLE_WIKI = (
    "Esta operação usa uma única wiki. Informe um nome só, ou omita para usar o padrão. "
    "Veja os nomes com `nix wiki list`."
)


@dataclass
class Runtime:
    """Índice, leitura e busca de uma wiki. O Embedder é do processo, não desta wiki."""

    config: NixConfig
    wiki: WikiSettings
    store: IndexStore
    vectors: VectorStore
    embedder: Embedder
    reader: WikiReader
    writer: WikiWriter
    indexer: Indexer
    writeback: Writeback
    retrieval: RetrievalService
    graph: WikiGraph

    @classmethod
    def from_config(cls, config: NixConfig, wiki: WikiSettings, embedder: Embedder) -> Runtime:
        configure_logging(config)
        config.require_wiki(wiki.name)
        prepare_native_imports()
        data_dir = config.wiki_index_dir(wiki)
        data_dir.mkdir(parents=True, exist_ok=True)
        store = IndexStore(data_dir / "index.db")
        vectors = VectorStore(data_dir / "chroma")
        reader = WikiReader(config, wiki)
        writer = WikiWriter(config, wiki, reader)
        graph = WikiGraph(store)
        indexer = Indexer(config, wiki, store, vectors, embedder, reader, on_change=graph.invalidate)
        writeback = Writeback(indexer)
        retrieval = RetrievalService(config, wiki, store, vectors, embedder)
        return cls(
            config=config,
            wiki=wiki,
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
            data_dir=str(self.config.wiki_index_dir(self.wiki)),
            warn_when_stale=self.config.index.warn_when_stale,
            wiki_name=self.wiki.name,
        )

    def close(self) -> None:
        self.store.close()
        self.vectors.close()


class RuntimeHost:
    """Runtimes do processo, um por wiki, recarregados quando o settings.db muda.

    A chave do mapa é o nome em minúsculas; o runtime guarda a grafia original.
    O runtime nasce na primeira resolução. `embedding_model` e a pasta-base do
    índice ficam os do processo vivo: trocar o modelo ainda pede reinício.
    Um runtime em sincronização não é fechado: a trava (ou o job da interface)
    segura ele até o fim, e o close acontece em seguida.
    """

    def __init__(self, config: NixConfig, *, capture_embedder_stdout: bool = True) -> None:
        from nix.config.store import SettingsStore

        configure_logging(config)
        prepare_native_imports()
        self._config = config
        self._embedder = Embedder(
            config.index.embedding_model,
            config.index.embedding_batch_size,
            capture_stdout=capture_embedder_stdout,
        )
        self._runtimes: dict[str, Runtime] = {}
        self._retired: list[Runtime] = []
        self._lock = threading.RLock()
        self._stamp = SettingsStore().updated_at()
        self._restart_notice: str | None = None
        add_sync_idle_listener(self._on_sync_idle)

    @property
    def config(self) -> NixConfig:
        return self._config

    @property
    def embedder(self) -> Embedder:
        return self._embedder

    @property
    def restart_notice(self) -> str | None:
        return self._restart_notice

    @property
    def runtime(self) -> Runtime:
        """Wiki padrão. Preferir `resolve` quando o nome vier da chamada."""
        return self.resolve(None)

    def resolve(self, name: str | None) -> Runtime:
        """Abre a wiki pedido, ou o padrão quando `name` é omitido."""
        if isinstance(name, str) and name.strip() == "*":
            raise ConfigError(_SINGLE_WIKI)
        with self._lock:
            wiki = self._one(name)
            self._config.require_wiki(wiki.name)
            return self._open(wiki)

    def resolve_many(self, spec: WikiSpec) -> OpenedWikis:
        """Um nome, uma lista ou ``*``. Nome que não está cadastrado falha a chamada inteira.

        Cada wiki cadastrado abre no próprio passo. Pasta ausente ou índice
        ilegível fica em `errors`, com a ação corretiva, e os outros seguem.
        `resolve` de um único nome continua falhando a chamada.
        """
        with self._lock:
            wikis = self._select(spec)
            runtimes: list[Runtime] = []
            errors: list[WikiOpenError] = []
            for wiki in wikis:
                try:
                    runtimes.append(self._open(wiki))
                except NixError as exc:
                    errors.append(_open_failure(wiki, exc.message))
                except sqlite3.Error as exc:
                    errors.append(_open_failure(wiki, _index_unreadable(wiki.name, exc)))
                except OSError as exc:
                    errors.append(_open_failure(wiki, _vault_unreadable(wiki.name, exc)))
            return OpenedWikis(runtimes, errors)

    def vaults_for(self, spec: WikiSpec) -> list[WikiSettings]:
        """As wikis do spec, sem abrir o índice. Nome desconhecido lista as cadastradas."""
        with self._lock:
            return self._select(spec)

    def before_call(self) -> str | None:
        from nix.config.loader import clear_config_cache, load_config
        from nix.config.store import SettingsStore
        from nix.core.errors import NixError

        with self._lock:
            stamp = SettingsStore().updated_at()
            if stamp == self._stamp:
                return self._restart_notice
            clear_config_cache()
            try:
                new_config = load_config(use_cache=False)
            except NixError as exc:
                return exc.message
            notice = _restart_notice(self._config, new_config)
            pinned = _pin_live_index(self._config, new_config)
            self._embedder.batch_size = pinned.index.embedding_batch_size
            configure_logging(pinned)
            if _same_settings(pinned, self._config):
                self._stamp = stamp
                self._restart_notice = notice
                return notice
            self._config = pinned
            self._stamp = stamp
            self._restart_notice = notice
            self._drop_removed()
            return notice

    def close(self) -> None:
        remove_sync_idle_listener(self._on_sync_idle)
        with self._lock:
            pending = {id(runtime): runtime for runtime in self._runtimes.values()}
            for runtime in self._retired:
                pending.setdefault(id(runtime), runtime)
            self._runtimes.clear()
            self._retired.clear()
        for runtime in pending.values():
            runtime.close()

    def _one(self, name: str | None) -> WikiSettings:
        if name is None or not name.strip():
            return self._config.default_wiki
        return self._config.get_wiki(name)

    def _select(self, spec: WikiSpec) -> list[WikiSettings]:
        if spec is None:
            return [self._config.default_wiki]
        if isinstance(spec, str):
            text = spec.strip()
            if not text:
                return [self._config.default_wiki]
            if text == "*":
                if not self._config.wikis:
                    raise ConfigError(
                        "Nenhuma wiki configurada. Rode `nix init` para cadastrar a primeira."
                    )
                return list(self._config.wikis)
            return [self._config.get_wiki(text)]
        if isinstance(spec, list):
            names = [item.strip() for item in spec if isinstance(item, str) and item.strip()]
            if len(names) != len(spec) or not names:
                raise ConfigError(
                    "Informe ao menos um nome de wiki, ou \"*\" para todos. "
                    "Veja os nomes com `nix wiki list`."
                )
            if any(item == "*" for item in names):
                raise ConfigError(
                    '"*" vale sozinho, para todas as wikis. Não misture com nomes. '
                    "Veja os nomes com `nix wiki list`."
                )
            chosen: list[WikiSettings] = []
            seen: set[str] = set()
            for item in names:
                wiki = self._config.get_wiki(item)
                key = wiki.name.casefold()
                if key in seen:
                    continue
                seen.add(key)
                chosen.append(wiki)
            return chosen
        raise ConfigError(
            'A wiki deve ser um nome, uma lista de nomes ou "*". Veja os nomes com `nix wiki list`.'
        )

    def _open(self, wiki: WikiSettings) -> Runtime:
        key = wiki.name.casefold()
        current = self._runtimes.get(key)
        if current is not None and current.config is self._config and _same_vault(current.wiki, wiki):
            return current
        # A sincronização ainda usa o cliente aberto. Um segundo Chroma no mesmo
        # diretório disputa o sqlite do índice; o próximo acesso, depois da trava, reabre.
        if current is not None and sync_in_progress(current.wiki.name):
            return current
        fresh = Runtime.from_config(self._config, wiki, self._embedder)
        previous = self._runtimes.get(key)
        self._runtimes[key] = fresh
        if previous is not None and previous is not fresh:
            self._retire(previous)
        return fresh

    def _drop_removed(self) -> None:
        """Fecha quem saiu da configuração e já não está em sincronização."""
        self._flush_idle_retired()
        live = {wiki.name.casefold() for wiki in self._config.wikis}
        for key in list(self._runtimes):
            if key in live:
                continue
            runtime = self._runtimes[key]
            if sync_in_progress(runtime.wiki.name):
                continue
            self._runtimes.pop(key)
            runtime.close()

    def _retire(self, runtime: Runtime) -> None:
        """Não fecha SQLite/Chroma enquanto a sincronização desta wiki ainda usa o objeto."""
        if sync_in_progress(runtime.wiki.name):
            self._retired.append(runtime)
            return
        runtime.close()

    def _flush_idle_retired(self) -> None:
        kept: list[Runtime] = []
        for runtime in self._retired:
            key = runtime.wiki.name.casefold()
            if runtime is self._runtimes.get(key) or sync_in_progress(runtime.wiki.name):
                kept.append(runtime)
                continue
            runtime.close()
        self._retired = kept

    def _on_sync_idle(self, name: str) -> None:
        """A trava soltou. Fecha o runtime se a wiki já saiu da configuração."""
        with self._lock:
            self._flush_idle_retired()
            key = name.strip().casefold()
            runtime = self._runtimes.get(key)
            if runtime is None or sync_in_progress(runtime.wiki.name):
                return
            live = {wiki.name.casefold() for wiki in self._config.wikis}
            if key in live:
                return
            self._runtimes.pop(key, None)
            runtime.close()


def _same_vault(left: WikiSettings, right: WikiSettings) -> bool:
    return left.model_dump(mode="json") == right.model_dump(mode="json")


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


def _open_failure(wiki: WikiSettings, message: str) -> WikiOpenError:
    return WikiOpenError(
        name=wiki.name,
        message=message,
        path=wiki.path,
        is_default=wiki.is_default,
    )


def _index_unreadable(name: str, exc: sqlite3.Error) -> str:
    return (
        f"Não foi possível ler o índice da wiki {name} ({exc}). "
        f"Rode `nix sync --wiki {name}` ou apague a pasta do índice dessa wiki e sincronize de novo."
    )


def _vault_unreadable(name: str, exc: OSError) -> str:
    return (
        f"Não foi possível abrir a wiki {name} ({exc}). "
        "Crie a pasta ou ajuste o caminho com `nix wiki` e tente de novo."
    )
