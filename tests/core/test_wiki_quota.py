"""Cenários de `bdd/` sobre a cota de wikis: HU-23."""

from __future__ import annotations

from pathlib import Path

import pytest

from nix.core.admin.wikis import WikiService
from nix.core.errors import ConfigError


def _add_wikis(service: WikiService, root: Path, count: int) -> None:
    """Cadastra `count` wikis em pastas irmãs, sem aninhar uma na outra."""
    root.mkdir(exist_ok=True)
    start = len(service.list_wikis())
    for offset in range(count):
        name = f"W{start + offset:03d}"
        folder = root / name
        folder.mkdir()
        service.add(name, folder)


@pytest.mark.bdd("HU-23.1")
def test_hundredth_wiki_is_accepted_and_one_default_remains(configured: Path, tmp_path: Path) -> None:
    service = WikiService()
    root = tmp_path / "cota"
    _add_wikis(service, root, 98)
    assert len(service.list_wikis()) == 99

    folder = root / "Centesima"
    folder.mkdir()
    added = service.add("Centesima", folder)

    wikis = service.list_wikis()
    defaults = [wiki.name for wiki in wikis if wiki.is_default]
    assert len(wikis) == 100
    assert added.name == "Centesima"
    assert defaults == ["Default"]


@pytest.mark.bdd("HU-23.2")
def test_wiki_past_the_hundred_is_refused(configured: Path, tmp_path: Path) -> None:
    service = WikiService()
    root = tmp_path / "cota"
    _add_wikis(service, root, 99)
    assert len(service.list_wikis()) == 100

    extra = root / "Extra"
    extra.mkdir()
    with pytest.raises(ConfigError) as refused:
        service.add("Extra", extra)

    assert "100" in refused.value.message
    assert "nix wiki remove" in refused.value.message
    names = [wiki.name for wiki in service.list_wikis()]
    assert len(names) == 100
    assert "Extra" not in names
