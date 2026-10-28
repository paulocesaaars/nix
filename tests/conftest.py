"""Fixtures comuns dos testes.

Todo teste roda isolado: `nix_home` é automático e aponta a pasta do aplicativo
para um diretório temporário, então nenhum teste toca no `settings.db` nem no
`.nix/` do checkout ou da instalação.

Testes que cobrem um cenário de `bdd/` levam o ID dele:

    @pytest.mark.bdd("HU-03.2")
    def test_sync_without_changes(...): ...
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest

from nix.config import paths
from nix.core.runtime import RuntimeHost

_FAKE_DIM = 64
_TOKEN = re.compile(r"\w+", re.UNICODE)


@pytest.fixture(autouse=True)
def nix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Pasta do aplicativo isolada: `settings.db` e `.nix/` nascem aqui."""
    home = tmp_path / "nix-home"
    home.mkdir()
    monkeypatch.setenv("NIX_HOME", str(home))
    # No checkout editável `app_root` venceria `$NIX_HOME`; desliga essa busca.
    monkeypatch.setattr(paths, "checkout_root", lambda: None)
    return home


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    """Vault temporário com notas, frontmatter, tags e links."""
    root = tmp_path / "vault"
    notes = {
        "Inbox/reuniao.md": "---\ntags: [reuniao]\n---\n# Reunião\n\nDecidimos validar CEP no cadastro.\n",
        "Projetos/ViaCEP/api.md": "# API ViaCEP\n\n## Endpoints\n\nConsulta de CEP. Ver [[reuniao]].\n",
        "Diario/2026-10-28.md": "# Diário\n\nRevisei a sincronização do índice. #nix\n",
    }
    for relative, content in notes.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


class FakeEmbedder:
    """Embedder determinístico e leve: troca o FastEmbed sem baixar o ONNX.

    Cada palavra cai num índice do vetor pelo hash; textos com palavras em comum
    ficam próximos, o que basta para a busca semântica se comportar nos testes.
    """

    def __init__(self, model_name: str, batch_size: int = 32, *, capture_stdout: bool = True) -> None:
        self.model_name = model_name
        self.batch_size = batch_size
        self.capture_stdout = capture_stdout

    def ensure_loaded(self) -> None:
        return None

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    @property
    def dim(self) -> int:
        return _FAKE_DIM

    @staticmethod
    def _vector(text: str) -> list[float]:
        vector = [0.0] * _FAKE_DIM
        for token in _TOKEN.findall(text.lower()):
            bucket = int.from_bytes(hashlib.blake2b(token.encode(), digest_size=4).digest(), "big")
            vector[bucket % _FAKE_DIM] += 1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


@pytest.fixture
def fake_embedder(monkeypatch: pytest.MonkeyPatch) -> type[FakeEmbedder]:
    """Faz o runtime usar o `FakeEmbedder` no lugar do modelo real."""
    monkeypatch.setattr("nix.core.runtime.Embedder", FakeEmbedder)
    return FakeEmbedder


@pytest.fixture
def configured(vault: Path, fake_embedder: type[FakeEmbedder]) -> Path:
    """Nix inicializado (`settings.db` em `nix_home`) com o vault temporário como padrão."""
    from nix.config.embedding_models import default_embedding_model
    from nix.config.loader import clear_config_cache
    from nix.core.admin.setup import initialize

    initialize(vault=vault, embedding_model=default_embedding_model(), force=False, update_embedding=True)
    clear_config_cache()
    return vault


@pytest.fixture
def host(configured: Path) -> Iterator[RuntimeHost]:
    """Runtimes do processo sobre o vault configurado; fechados ao fim do teste."""
    from nix.config.loader import load_config

    runtime_host = RuntimeHost(load_config())
    try:
        yield runtime_host
    finally:
        runtime_host.close()
