"""Cenário de `bdd/` sobre a ficha no MCP Registry: HU-24."""

from __future__ import annotations

import hashlib

import pytest

from nix.mcp.registry import server_json

_VERSION = "4.0.0"
_TAG = "v4.0.0"
_REPO = "paulocesaaars/nix"
_MCPB = (
    "nix-4.0.0-windows-amd64.mcpb",
    "nix-4.0.0-linux-amd64.mcpb",
    "nix-4.0.0-linux-arm64.mcpb",
    "nix-4.0.0-darwin-arm64.mcpb",
)
_TITLES = {
    "nix-4.0.0-windows-amd64.mcpb": "Windows amd64",
    "nix-4.0.0-linux-amd64.mcpb": "Linux amd64",
    "nix-4.0.0-linux-arm64.mcpb": "Linux arm64",
    "nix-4.0.0-darwin-arm64.mcpb": "macOS arm64",
}


@pytest.mark.bdd("HU-24.1")
def test_registry_card_points_at_release_mcpb() -> None:
    digests = {name: hashlib.sha256(name.encode()).hexdigest() for name in _MCPB}
    lines = [f"{digests[name]}  {name}" for name in _MCPB]
    lines.append(f"{'ab' * 32}  nix-4.0.0-linux-amd64")
    lines.append(f"{'cd' * 32}  nix-hook-4.0.0-linux-amd64")

    card = server_json(version=_VERSION, tag=_TAG, repo=_REPO, checksums="\n".join(lines) + "\n")

    assert card["name"] == "io.github.paulocesaaars/nix"
    assert card["version"] == _VERSION
    assert card["$schema"] == "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json"
    packages = card["packages"]
    assert [package["identifier"].rsplit("/", 1)[-1] for package in packages] == list(_MCPB)
    for package in packages:
        filename = package["identifier"].rsplit("/", 1)[-1]
        assert package["registryType"] == "mcpb"
        assert package["transport"] == {"type": "stdio"}
        assert package["fileSha256"] == digests[filename]
        assert package["identifier"] == (
            f"https://github.com/{_REPO}/releases/download/{_TAG}/{filename}"
        )
        assert package["title"] == _TITLES[filename]
        assert set(package) == {"registryType", "identifier", "version", "fileSha256", "transport", "title"}
