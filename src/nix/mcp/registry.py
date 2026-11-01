"""MCPB da release e a ficha `server.json` do MCP Registry.

O schema vigente (2025-12-11) não declara filtro de sistema nem de arquitetura,
nem `title` ou `description` no pacote. Cada plataforma compilada vira um
pacote `mcpb` distinto, apontando para a URL do artefato. O `title` de cada
pacote — campo extra aceito, porque o schema não proíbe propriedades
adicionais — traz o sistema e a arquitetura em texto. O manifesto dentro do
MCPB usa `compatibility.platforms` com os valores oficiais (`darwin`, `win32`,
`linux`).
"""

from __future__ import annotations

import io
import json
import re
import stat
import zipfile
from pathlib import Path
from typing import Any

SERVER_NAME = "io.github.paulocesaaars/nix"
SCHEMA_URL = "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json"
DESCRIPTION = "Servidor MCP stdio para wikis em Markdown"
REPOSITORY = "paulocesaaars/nix"
MANIFEST_VERSION = "0.3"

# sistema do nome do binário, arquitetura, plataforma do manifesto MCPB.
RELEASE_TARGETS: tuple[tuple[str, str, str], ...] = (
    ("windows", "amd64", "win32"),
    ("linux", "amd64", "linux"),
    ("linux", "arm64", "linux"),
    ("darwin", "arm64", "darwin"),
)

_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_PACKAGE_ICON = "src/nix/mcp/nix.png"
_OS_LABEL = {"windows": "Windows", "linux": "Linux", "darwin": "macOS"}


class RegistryError(Exception):
    """Ficha ou MCPB que não pode ser gerado. A mensagem diz o que corrigir."""


def binary_filename(version: str, system: str, arch: str) -> str:
    """Nome do binário publicado, o mesmo de `scripts/build_frozen.py`."""
    suffix = ".exe" if system == "windows" else ""
    return f"nix-{version}-{system}-{arch}{suffix}"


def mcpb_filename(version: str, system: str, arch: str) -> str:
    return f"nix-{version}-{system}-{arch}.mcpb"


def release_asset_url(repo: str, tag: str, filename: str) -> str:
    return f"https://github.com/{repo}/releases/download/{tag}/{filename}"


def parse_checksums(text: str) -> dict[str, str]:
    """Lê a saída do `sha256sum` (digest em hex minúsculo e o nome do arquivo)."""
    found: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            raise RegistryError(
                "Uma linha dos checksums não tem digest e nome. Rode `sha256sum nix-*` de novo."
            )
        digest, filename = parts
        filename = filename.lstrip("*")
        if filename in found:
            raise RegistryError(
                f"O checksum de {filename} aparece duas vezes. "
                "Rode o `sha256sum` de novo, uma linha por arquivo."
            )
        if _SHA256.fullmatch(digest) is None:
            raise RegistryError(
                f"O checksum de {filename} não é um SHA-256 em hex minúsculo. "
                "Rode `sha256sum` de novo no passo dos checksums."
            )
        found[filename] = digest
    return found


def server_json(*, version: str, tag: str, repo: str, checksums: str) -> dict[str, Any]:
    """Ficha da release. O SHA de cada MCPB sai do texto dos checksums, sem recalcular."""
    _require_release(version, tag, repo)
    if len(DESCRIPTION) > 100:
        raise RegistryError(
            "A descrição da ficha passa de 100 caracteres. Encurte DESCRIPTION antes de publicar."
        )
    digests = parse_checksums(checksums)
    packages: list[dict[str, Any]] = []
    for system, arch, _platform in RELEASE_TARGETS:
        filename = mcpb_filename(version, system, arch)
        digest = digests.get(filename)
        if digest is None:
            raise RegistryError(
                f"Não achei o checksum de {filename}. "
                "Gere o MCPB dessa plataforma antes do `sha256sum`."
            )
        packages.append(
            {
                "registryType": "mcpb",
                "identifier": release_asset_url(repo, tag, filename),
                "version": version,
                "fileSha256": digest,
                "transport": {"type": "stdio"},
                "title": _package_title(system, arch),
            }
        )
    return {
        "$schema": SCHEMA_URL,
        "name": SERVER_NAME,
        "title": "Nix",
        "description": DESCRIPTION,
        "version": version,
        "repository": {
            "url": f"https://github.com/{repo}",
            "source": "github",
        },
        "packages": packages,
    }


def build_mcpb(
    *,
    version: str,
    system: str,
    mcp_platform: str,
    binary: bytes,
    icon: bytes,
    repo: str = REPOSITORY,
) -> bytes:
    """ZIP com `manifest.json` na raiz e o binário em `server/`."""
    if mcp_platform not in {"darwin", "win32", "linux"}:
        raise RegistryError(
            f"Plataforma MCPB {mcp_platform!r} inválida. Use darwin, win32 ou linux."
        )
    if not icon.startswith(b"\x89PNG\r\n\x1a\n"):
        raise RegistryError(f"O ícone do MCPB precisa ser um PNG. Use o arquivo do pacote, {_PACKAGE_ICON}.")
    entry = "nix.exe" if system == "windows" else "nix"
    # O host acrescenta `.exe` no Windows. O comando fica sem sufixo; o arquivo, não.
    document = {
        "manifest_version": MANIFEST_VERSION,
        "name": "nix",
        "display_name": "Nix",
        "version": version,
        "description": DESCRIPTION,
        "author": {"name": "Paulo"},
        "license": "MIT",
        "repository": {"type": "git", "url": f"https://github.com/{repo}.git"},
        "icon": "icon.png",
        "server": {
            "type": "binary",
            "entry_point": f"server/{entry}",
            "mcp_config": {"command": "server/nix", "args": [], "env": {}},
        },
        "tools_generated": True,
        "compatibility": {"platforms": [mcp_platform]},
    }
    payload = json.dumps(document, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        _add(archive, "manifest.json", payload, 0o644)
        _add(archive, "icon.png", icon, 0o644)
        _add(archive, f"server/{entry}", binary, 0o755, stored=True)
    return buffer.getvalue()


def pack_release(artifacts: Path, version: str, icon_path: Path, repo: str = REPOSITORY) -> list[Path]:
    """Grava um MCPB por plataforma já compilada. Falha se algum binário faltar."""
    _require_release(version, f"v{version}", repo)
    if not icon_path.is_file():
        raise RegistryError(
            f"Não achei o ícone em {icon_path.as_posix()}. O MCPB usa o PNG do pacote, {_PACKAGE_ICON}."
        )
    icon = icon_path.read_bytes()
    written: list[Path] = []
    for system, arch, platform in RELEASE_TARGETS:
        binary_path = artifacts / binary_filename(version, system, arch)
        if not binary_path.is_file():
            raise RegistryError(
                f"Não achei o binário {binary_path.name} em {artifacts}. "
                "Compile essa plataforma e rode este passo de novo."
            )
        payload = build_mcpb(
            version=version,
            system=system,
            mcp_platform=platform,
            binary=binary_path.read_bytes(),
            icon=icon,
            repo=repo,
        )
        dest = artifacts / mcpb_filename(version, system, arch)
        dest.write_bytes(payload)
        written.append(dest)
    return written


def _package_title(system: str, arch: str) -> str:
    """Sistema e arquitetura legíveis. O schema não tem filtro; o title distingue o pacote."""
    name = _OS_LABEL.get(system)
    if name is None:
        raise RegistryError(
            f"Sistema {system!r} sem nome legível. Use windows, linux ou darwin em RELEASE_TARGETS."
        )
    return f"{name} {arch}"


def _require_release(version: str, tag: str, repo: str) -> None:
    if not version or any(char in version for char in "/\\ "):
        raise RegistryError(
            f"Versão {version!r} inválida. Use o número do pyproject, como 5.0.1."
        )
    if tag != f"v{version}" or any(char in tag for char in "/\\ "):
        raise RegistryError(
            f"A tag {tag!r} não corresponde à versão {version}. "
            "Publique com a tag vX.Y.Z dessa mesma release."
        )
    owner, _sep, name = repo.partition("/")
    if not owner or not name or "/" in name or " " in repo:
        raise RegistryError(
            f"Repositório {repo!r} inválido. Use owner/nome, como paulocesaaars/nix."
        )


def _add(archive: zipfile.ZipFile, name: str, data: bytes, mode: int, *, stored: bool = False) -> None:
    info = zipfile.ZipInfo(name)
    info.compress_type = zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | mode) << 16
    archive.writestr(info, data)
