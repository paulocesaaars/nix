"""O initialize declara um PNG pequeno derivado do nix.png do pacote."""

from __future__ import annotations

import base64
from importlib.resources import files

from nix.mcp.server import build_server


def test_server_declares_png_icon() -> None:
    server = build_server()
    info = server._lowlevel_server.server_info
    icons = info.icons
    assert icons is not None and len(icons) == 1
    icon = icons[0]
    assert server.icons == list(icons)
    assert icon.mime_type == "image/png"
    assert icon.src.startswith("data:image/png;base64,")
    assert "://" not in icon.src.split(",", 1)[0]
    raw = base64.b64decode(icon.src.removeprefix("data:image/png;base64,"), validate=True)
    small = files("nix.mcp").joinpath("nix-48.png").read_bytes()
    source = files("nix.mcp").joinpath("nix.png").read_bytes()
    assert raw == small
    assert len(raw) < len(source)
    width = int.from_bytes(raw[16:20], "big")
    height = int.from_bytes(raw[20:24], "big")
    assert (width, height) == (48, 48)
    assert icon.sizes == [f"{width}x{height}"]
