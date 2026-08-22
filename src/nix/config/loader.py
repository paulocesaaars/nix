"""Carregamento da configuração: env > arquivo TOML > padrão."""

from __future__ import annotations

import contextlib
import os
import tomllib
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from nix.config.paths import app_root, default_config_path, resolve_app_path
from nix.config.schema import NixConfig
from nix.core.errors import ConfigError

_cached: NixConfig | None = None

_KNOWN_SECTIONS = frozenset({"vault", "index", "retrieval", "safety", "logging"})
_LEGACY_HINTS: dict[str, str] = {
    "openai": "A seção [openai] não é mais usada; o Nix não chama LLM. Remova-a do TOML.",
    "agent": (
        "A seção [agent] não é mais usada. Migre agent.longterm_folder para "
        "vault.longterm_folder e remova [agent]."
    ),
    "mcp": "A seção [mcp] não é mais usada (transporte só stdio). Remova-a do TOML.",
    "limits": "A seção [limits] não é mais usada. Remova-a do TOML.",
}


def config_write_path() -> Path:
    """Destino do `nix init` e do TOML canônico: `$NIX_CONFIG` ou `{app_root}/nix.toml`."""
    env = os.environ.get("NIX_CONFIG")
    if env and env.strip():
        return resolve_app_path(env.strip(), app_root())
    return default_config_path()


def _config_candidates(explicit: Path | None) -> list[Path]:
    if explicit is not None:
        return [explicit]
    env = os.environ.get("NIX_CONFIG")
    if env and env.strip():
        return [resolve_app_path(env.strip(), app_root())]

    candidates: list[Path] = []
    seen: set[str] = set()

    def add(path: Path) -> None:
        try:
            key = str(path.resolve()).casefold()
        except OSError:
            key = str(path).casefold()
        if key in seen:
            return
        seen.add(key)
        candidates.append(path)

    add(default_config_path())
    here = Path.cwd()
    with contextlib.suppress(OSError):
        here = here.resolve()
    for directory in [here, *here.parents]:
        add(directory / "nix.toml")
    return candidates


def resolve_config_path(explicit: Path | None = None) -> Path | None:
    """Retorna o primeiro arquivo existente na ordem de busca."""
    for path in _config_candidates(explicit):
        if path.is_file():
            return path
    return None


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except OSError as exc:
        raise ConfigError(
            f"Não foi possível ler {path}: {exc}. Verifique permissões e o caminho em NIX_CONFIG."
        ) from exc
    except tomllib.TOMLDecodeError as exc:
        extra = ""
        detail = str(exc).lower()
        if "hex" in detail or "escape" in detail or "\\u" in detail:
            extra = (
                " Em caminhos Windows use barras / "
                "(ex.: C:/Obsidian/MeuVault) ou dobre as invertidas "
                "(C:\\\\Obsidian\\\\MeuVault). Uma única \\ antes de U/x/n é escape TOML."
            )
        raise ConfigError(
            f"TOML inválido em {path}: {exc}.{extra} "
            "Corrija a sintaxe ou rode `nix init` de novo."
        ) from exc
    if not isinstance(data, dict):
        raise ConfigError(
            f"{path} não contém uma tabela TOML na raiz. Use o template gerado por `nix init`."
        )
    return data


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _env_overrides() -> dict[str, Any]:
    """Lê NIX_SECTION__FIELD. Env ganha do arquivo."""
    result: dict[str, Any] = {}
    prefix = "NIX_"
    nested: dict[str, dict[str, Any]] = {}
    for raw_key, raw_value in os.environ.items():
        if not raw_key.startswith(prefix) or raw_key == "NIX_CONFIG":
            continue
        rest = raw_key[len(prefix) :]
        if "__" not in rest:
            continue
        section, field = rest.split("__", 1)
        section = section.lower()
        field = field.lower()
        nested.setdefault(section, {})[field] = _coerce_env(raw_value)
    if nested:
        result.update(nested)
    return result


def _coerce_env(value: str) -> Any:
    lowered = value.strip().lower()
    if lowered in {"true", "1", "yes", "on"}:
        return True
    if lowered in {"false", "0", "no", "off"}:
        return False
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _format_validation(exc: ValidationError) -> str:
    parts: list[str] = []
    for err in exc.errors():
        loc = ".".join(str(item) for item in err["loc"])
        msg = err["msg"]
        parts.append(f"{loc}: {msg}")
    joined = "; ".join(parts)
    return (
        f"Configuração inválida ({joined}). Corrija o arquivo apontado por "
        "`nix doctor` ou as variáveis NIX_*."
    )


def _apply_legacy(data: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Detecta seções desconhecidas e migra agent.longterm_folder se preciso."""
    unknown = [key for key in data if key not in _KNOWN_SECTIONS and key != "config_path"]
    warnings: list[str] = []
    for key in unknown:
        hint = _LEGACY_HINTS.get(key)
        if hint:
            warnings.append(hint)
        else:
            warnings.append(
                f"Seção [{key}] no TOML não é reconhecida e será ignorada. "
                "Confira o template gerado por `nix init`."
            )
    agent = data.get("agent")
    vault = data.get("vault")
    if isinstance(agent, dict) and "longterm_folder" in agent:
        vault_table = dict(vault) if isinstance(vault, dict) else {}
        if "longterm_folder" not in vault_table:
            vault_table["longterm_folder"] = agent["longterm_folder"]
            data["vault"] = vault_table
            warnings.append(
                "Copiei agent.longterm_folder para vault.longterm_folder nesta sessão. "
                "Edite o TOML para persistir a mudança."
            )
    return unknown, warnings


def load_config(
    path: Path | None = None,
    *,
    require_file: bool = False,
    use_cache: bool = True,
) -> NixConfig:
    """Carrega e valida a configuração. Precedência: env > arquivo > padrão."""
    global _cached
    if use_cache and _cached is not None and path is None:
        return _cached

    resolved = resolve_config_path(path)
    data: dict[str, Any] = {}
    if resolved is not None and resolved.is_file():
        data = _read_toml(resolved)
    elif require_file:
        hint = path or config_write_path()
        raise ConfigError(
            f"Arquivo de configuração não encontrado em {hint}. Rode `nix init` para criá-lo."
        )

    merged = _deep_merge(data, _env_overrides())
    merged.pop("config_path", None)
    unknown, legacy_warnings = _apply_legacy(merged)
    try:
        anchor = resolved.parent if resolved is not None else app_root()
        config = NixConfig.model_validate(merged, context={"path_anchor": anchor})
    except (ValidationError, ConfigError) as exc:
        if isinstance(exc, ConfigError):
            raise
        raise ConfigError(_format_validation(exc)) from exc

    config.config_path = resolved
    config.unknown_sections = unknown
    config.legacy_warnings = legacy_warnings
    if use_cache and path is None:
        _cached = config
    return config


def clear_config_cache() -> None:
    global _cached
    _cached = None


def public_dict(config: NixConfig) -> dict[str, Any]:
    """Serializa a config para exibição."""
    return config.model_dump(mode="json")
