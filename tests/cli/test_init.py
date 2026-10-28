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
from nix.core.admin.vaults import VaultService

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
    """Cópia da config com o caminho dos vaults apagado, para comparar o resto."""
    cloned: dict[str, Any] = json.loads(json.dumps(dump))
    for item in cloned["vaults"]:
        item["path"] = ""
    return cloned


@pytest.mark.bdd("HU-01.2")
def test_init_with_all_options_does_not_prompt(vault: Path) -> None:
    result = runner.invoke(
        app,
        ["init", "--name", "Pessoal", "--vault", str(vault), "--embedding-model", "1"],
    )

    assert result.exit_code == 0, result.output
    vaults = VaultService().list_vaults()
    assert [item.name for item in vaults] == ["Pessoal"]
    assert Path(vaults[0].path) == vault.resolve()
    assert "Configuração concluída" in result.output


@pytest.mark.bdd("HU-01.4")
def test_init_refuses_name_when_vaults_exist(vault: Path, tmp_path: Path) -> None:
    first = runner.invoke(app, ["init", "--vault", str(vault), "--embedding-model", "1"])
    assert first.exit_code == 0, first.output

    again = runner.invoke(app, ["init", "--name", "Outro", "--vault", str(vault)])

    assert again.exit_code != 0
    assert "nix vault add" in again.output


@pytest.mark.bdd("HU-01.1")
def test_init_prompts_default_vault_and_model(vault: Path, nix_home: Path) -> None:
    # O prompt recebe o caminho nativo (com \ no Windows); o settings.db grava com /.
    result = prompt_runner.invoke(app, ["init"], input=_answers(str(vault), "1"))

    assert result.exit_code == 0, result.output
    assert (nix_home / "settings.db").is_file()
    vaults = VaultService().list_vaults()
    assert [item.name for item in vaults] == ["Default"]
    assert vaults[0].path == vault.resolve().as_posix()
    assert "/" in vaults[0].path
    assert "\\" not in vaults[0].path
    stored = SettingsStore().load_overrides()
    assert stored["index"]["embedding_model"] == EMBEDDING_MODELS[0].name


@pytest.mark.bdd("HU-01.3")
def test_init_without_force_updates_only_default_path(configured: Path, second_vault: Path) -> None:
    top_k = runner.invoke(app, ["config", "set", "retrieval.top_k", "9"])
    assert top_k.exit_code == 0, top_k.output
    clear_config_cache()
    before = load_config().model_dump(mode="json")
    assert before["retrieval"]["top_k"] == 9

    result = runner.invoke(app, ["init", "--vault", str(second_vault)])

    assert result.exit_code == 0, result.output
    clear_config_cache()
    after = load_config().model_dump(mode="json")
    assert after["vaults"][0]["path"] == second_vault.resolve().as_posix()
    assert after["vaults"][0]["path"] != before["vaults"][0]["path"]
    assert after["retrieval"]["top_k"] == 9
    assert _without_paths(before) == _without_paths(after)


@pytest.mark.bdd("HU-01.5")
def test_init_creates_missing_vault_directory(tmp_path: Path) -> None:
    missing = tmp_path / "vault-novo"
    result = prompt_runner.invoke(app, ["init"], input=_answers(str(missing), "y", "1"))

    assert result.exit_code == 0, result.output
    assert missing.is_dir()
    vaults = VaultService().list_vaults()
    assert [item.name for item in vaults] == ["Default"]
    assert vaults[0].path == missing.resolve().as_posix()
