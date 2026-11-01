"""Cenários de `bdd/` sobre o `nix init`: HU-01."""

from __future__ import annotations

import contextlib
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from nix.cli.app import app
from nix.config.embedding_models import EMBEDDING_MODELS
from nix.config.loader import clear_config_cache, load_config
from nix.config.store import SettingsStore
from nix.core.admin.wikis import WikiService

runner = CliRunner()


class _PromptRunner(CliRunner):
    """O Typer monta o stdin com isatty() falso; o init só pergunta num terminal."""

    @contextlib.contextmanager
    def isolation(
        self,
        input: str | bytes | None = None,
        env: Any = None,
        color: bool = False,
    ) -> Iterator[tuple[Any, Any, Any]]:
        with super().isolation(input=input, env=env, color=color) as streams:
            raw = sys.stdin

            class _TtyStdin:
                def isatty(self) -> bool:
                    return True

                def __getattr__(self, name: str) -> Any:
                    return getattr(raw, name)

            sys.stdin = _TtyStdin()  # type: ignore[assignment]
            try:
                yield streams
            finally:
                sys.stdin = raw


prompt_runner = _PromptRunner()


def _answers(*lines: str) -> str:
    return "".join(f"{line}\n" for line in lines)


def _without_paths(dump: dict[str, Any]) -> dict[str, Any]:
    """Cópia da config com o caminho das wikis apagado, para comparar o resto."""
    cloned: dict[str, Any] = json.loads(json.dumps(dump))
    for item in cloned["wikis"]:
        item["path"] = ""
    return cloned


@pytest.mark.bdd("HU-01.2")
def test_init_with_all_options_does_not_prompt(wiki: Path) -> None:
    result = runner.invoke(
        app,
        ["init", "--name", "Pessoal", "--wiki", str(wiki), "--embedding-model", "1"],
    )

    assert result.exit_code == 0, result.output
    wikis = WikiService().list_wikis()
    assert [item.name for item in wikis] == ["Pessoal"]
    assert Path(wikis[0].path) == wiki.resolve()
    assert "Configuração concluída" in result.output


@pytest.mark.bdd("HU-01.4")
def test_init_refuses_name_when_vaults_exist(wiki: Path, tmp_path: Path) -> None:
    first = runner.invoke(app, ["init", "--wiki", str(wiki), "--embedding-model", "1"])
    assert first.exit_code == 0, first.output

    again = runner.invoke(app, ["init", "--name", "Outro", "--wiki", str(wiki)])

    assert again.exit_code != 0
    assert "nix wiki add" in " ".join(again.output.split())


@pytest.mark.bdd("HU-01.1")
def test_init_prompts_default_vault_and_model(wiki: Path, nix_home: Path) -> None:
    # O prompt recebe o caminho nativo (com \ no Windows); o settings.db grava com /.
    result = prompt_runner.invoke(app, ["init"], input=_answers(str(wiki), "1"))

    assert result.exit_code == 0, result.output
    assert (nix_home / "settings.db").is_file()
    wikis = WikiService().list_wikis()
    assert [item.name for item in wikis] == ["Default"]
    assert wikis[0].path == wiki.resolve().as_posix()
    assert "/" in wikis[0].path
    assert "\\" not in wikis[0].path
    stored = SettingsStore().load_overrides()
    assert stored["index"]["embedding_model"] == EMBEDDING_MODELS[0].name


@pytest.mark.bdd("HU-01.3")
def test_init_without_force_updates_only_default_path(configured: Path, second_wiki: Path) -> None:
    top_k = runner.invoke(app, ["config", "set", "retrieval.top_k", "9"])
    assert top_k.exit_code == 0, top_k.output
    clear_config_cache()
    before = load_config().model_dump(mode="json")
    assert before["retrieval"]["top_k"] == 9

    result = runner.invoke(app, ["init", "--wiki", str(second_wiki)])

    assert result.exit_code == 0, result.output
    clear_config_cache()
    after = load_config().model_dump(mode="json")
    assert after["wikis"][0]["path"] == second_wiki.resolve().as_posix()
    assert after["wikis"][0]["path"] != before["wikis"][0]["path"]
    assert after["retrieval"]["top_k"] == 9
    assert _without_paths(before) == _without_paths(after)


@pytest.mark.bdd("HU-01.5")
def test_init_creates_missing_vault_directory(tmp_path: Path) -> None:
    missing = tmp_path / "wiki-novo"
    result = prompt_runner.invoke(app, ["init"], input=_answers(str(missing), "y", "1"))

    assert result.exit_code == 0, result.output
    assert missing.is_dir()
    wikis = WikiService().list_wikis()
    assert [item.name for item in wikis] == ["Default"]
    assert wikis[0].path == missing.resolve().as_posix()
