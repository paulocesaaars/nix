"""Edição linha a linha do frontmatter YAML, preservando o que não mudou.

Só a chave alterada é reemitida pelo PyYAML. Comentários, ordem e aspas das
demais linhas do bloco permanecem. Sem dependência nova: o PyYAML já vem com
o python-frontmatter.
"""

from __future__ import annotations

import re
from typing import Any

import yaml

from nix.core.errors import VaultError

_TOP_KEY = re.compile(r"^([^:#]+?):\s*(.*)$")


def _validate(yaml_text: str) -> None:
    if not yaml_text.strip():
        return
    try:
        loaded = yaml.safe_load(yaml_text)
    except yaml.YAMLError as exc:
        raise VaultError(
            f"O frontmatter resultante é YAML inválido ({exc}). "
            "A nota não foi alterada. Corrija os valores e tente de novo."
        ) from exc
    if loaded is None:
        return
    if not isinstance(loaded, dict):
        raise VaultError(
            "O frontmatter resultante não é um mapa YAML. "
            "A nota não foi alterada. Use chaves de topo, por exemplo `tags: [a, b]`."
        )


def _newline(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def _key_of(line: str) -> str | None:
    if not line or line[0] in " \t#-" or line.lstrip().startswith("#"):
        return None
    match = _TOP_KEY.match(line)
    if not match:
        return None
    key = match.group(1).strip().strip("'\"")
    if not key:
        return None
    return key


def _continues(line: str) -> bool:
    if line.startswith((" ", "\t")):
        return True
    stripped = line.strip()
    return bool(stripped) and stripped.startswith("-")


def _spans(lines: list[str]) -> list[tuple[str, int, int]]:
    """Intervalos [início, fim) de cada chave de topo, com as linhas de continuação."""
    spans: list[tuple[str, int, int]] = []
    index = 0
    total = len(lines)
    while index < total:
        key = _key_of(lines[index])
        if key is None:
            index += 1
            continue
        start = index
        index += 1
        while index < total:
            current = lines[index]
            if _key_of(current) is not None:
                break
            if _continues(current):
                index += 1
                continue
            if not current.strip():
                look = index + 1
                while look < total and not lines[look].strip():
                    look += 1
                if look < total and _continues(lines[look]):
                    index += 1
                    continue
            break
        spans.append((key, start, index))
    return spans


def _dump_key(key: str, value: object, newline: str) -> list[str]:
    dumped = yaml.safe_dump({key: value}, allow_unicode=True, sort_keys=False)
    if not isinstance(dumped, str):
        dumped = str(dumped)
    dumped = dumped.replace("\r\n", "\n").strip("\n")
    if newline != "\n":
        dumped = dumped.replace("\n", newline)
    return dumped.splitlines()


def _join(lines: list[str], newline: str) -> str:
    if not lines:
        return ""
    text = newline.join(lines)
    if not text.endswith(("\n", "\r\n")):
        text += newline
    return text


def _apply(
    yaml_text: str,
    updates: dict[str, Any],
    remove: set[str],
) -> str:
    newline = _newline(yaml_text)
    lines = yaml_text.splitlines()
    spans = _spans(lines)
    present = {key for key, _start, _end in spans}
    replace_at: dict[int, tuple[int, list[str]]] = {}
    delete: set[int] = set()
    replaced: set[str] = set()
    for key, start, end in spans:
        if key in remove or (key in updates and key in replaced):
            delete.update(range(start, end))
            continue
        if key in updates:
            replace_at[start] = (end, _dump_key(key, updates[key], newline))
            replaced.add(key)
    rebuilt: list[str] = []
    index = 0
    while index < len(lines):
        if index in replace_at:
            end, dumped = replace_at[index]
            rebuilt.extend(dumped)
            index = end
            continue
        if index in delete:
            index += 1
            continue
        rebuilt.append(lines[index])
        index += 1
    for key, value in updates.items():
        if key not in present:
            rebuilt.extend(_dump_key(key, value, newline))
    text = _join(rebuilt, newline)
    _validate(text)
    return text


def set_keys(yaml_text: str, updates: dict[str, Any]) -> str:
    """Substitui ou acrescenta chaves de topo. Chave nova vai para o fim do bloco."""
    if not updates:
        _validate(yaml_text)
        return yaml_text
    return _apply(yaml_text, updates, set())


def remove_keys(yaml_text: str, keys: list[str]) -> str:
    """Remove chaves de topo. Chave ausente é ignorada."""
    if not keys:
        _validate(yaml_text)
        return yaml_text
    return _apply(yaml_text, {}, set(keys))
