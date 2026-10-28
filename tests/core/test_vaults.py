"""Cenários de `bdd/` sobre o cadastro de vaults: HU-10 (nome inexistente) e HU-13 (sempre há um padrão)."""

from __future__ import annotations

from pathlib import Path

import pytest

from nix.core.admin.vaults import VaultService
from nix.core.errors import ConfigError
from nix.core.runtime import RuntimeHost


def _second_vault(tmp_path: Path) -> Path:
    other = tmp_path / "other-vault"
    other.mkdir()
    return other


@pytest.mark.bdd("HU-10.1")
def test_unknown_vault_error_lists_existing_vaults_and_default(configured: Path, host: RuntimeHost) -> None:
    with pytest.raises(ConfigError) as from_command:
        VaultService().set_default("missing")
    with pytest.raises(ConfigError) as from_tool:
        host.resolve("missing")

    for error in (from_command.value, from_tool.value):
        assert "Default" in error.message
        assert "padrão" in error.message


@pytest.mark.bdd("HU-10.2")
def test_vault_name_match_ignores_case(configured: Path) -> None:
    chosen = VaultService().set_default("default")

    assert chosen.name == "Default"


@pytest.mark.bdd("HU-13.1")
def test_default_vault_cannot_be_removed_until_another_is_chosen(configured: Path, tmp_path: Path) -> None:
    service = VaultService()
    service.add("Second", _second_vault(tmp_path))

    with pytest.raises(ConfigError) as refused:
        service.remove("Default")
    assert "nix vault default" in refused.value.message

    service.set_default("Second")
    service.remove("Default")
    assert [vault.name for vault in service.list_vaults()] == ["Second"]


@pytest.mark.bdd("HU-13.2")
def test_only_vault_cannot_be_removed(configured: Path) -> None:
    with pytest.raises(ConfigError) as refused:
        VaultService().remove("Default")

    assert "único" in refused.value.message
    assert [vault.name for vault in VaultService().list_vaults()] == ["Default"]
