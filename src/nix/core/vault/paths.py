"""Normalização e confinamento de caminhos ao vault (RN-03)."""

from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path, PurePosixPath

from nix.core.errors import PathEscapeError

_UNSAFE_PARTS = {"", ".", ".."}


def to_posix(rel_path: str) -> str:
    return rel_path.replace("\\", "/").lstrip("/")


def match_glob(rel_posix: str, pattern: str) -> bool:
    """Glob estilo git, com suporte a `**`."""
    pat = pattern.replace("\\", "/")
    if rel_posix == pat or fnmatch(rel_posix, pat):
        return True
    if pat.startswith("**/"):
        rest = pat[3:]
        if fnmatch(rel_posix, rest) or fnmatch(PurePosixPath(rel_posix).name, rest):
            return True
        parts = rel_posix.split("/")
        for i in range(len(parts)):
            if fnmatch("/".join(parts[i:]), rest):
                return True
    if pat.endswith("/**"):
        prefix = pat[:-3]
        return rel_posix == prefix or rel_posix.startswith(prefix + "/")
    if "/**/" in pat:
        head, tail = pat.split("/**/", 1)
        if head and not rel_posix.startswith(head.rstrip("/") + "/") and rel_posix != head:
            return False
        return fnmatch(rel_posix, pat) or rel_posix.endswith("/" + tail) or fnmatch(
            PurePosixPath(rel_posix).name, tail
        )
    return False


def is_included(
    rel_path: str,
    include: list[str],
    exclude: list[str],
    *,
    apply_include: bool = True,
) -> bool:
    posix = to_posix(rel_path)
    if apply_include and include and not any(match_glob(posix, pattern) for pattern in include):
        return False
    return not any(match_glob(posix, pattern) for pattern in exclude)


def assert_accessible(
    rel_path: str,
    include: list[str],
    exclude: list[str],
    *,
    apply_include: bool = True,
) -> str:
    """Garante RN-06: notas excluídas não são lidas, escritas nem indexadas."""
    posix = to_posix(rel_path)
    if not is_included(posix, include, exclude, apply_include=apply_include):
        raise PathEscapeError(
            f"{posix} está excluída pelos filtros include/exclude do vault. "
            "Ajuste vault.exclude (ou include) na configuração se precisar acessá-la."
        )
    return posix


def matches_folder(rel_path: str, folder: str | None) -> bool:
    """True se a nota está na pasta ou em uma subpasta."""
    if not folder or not folder.strip():
        return True
    folder_n = folder.strip("/").replace("\\", "/")
    posix = to_posix(rel_path)
    return posix == folder_n or posix.startswith(folder_n + "/")



def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def resolve_in_vault(
    vault_root: Path,
    rel_path: str,
    *,
    follow_symlinks: bool = False,
) -> Path:
    """Resolve `rel_path` dentro do vault. Rejeita absoluto, `..` e symlink que escape."""
    if not rel_path or not rel_path.strip():
        raise PathEscapeError(
            "Caminho relativo vazio. Informe um caminho como Notas/Exemplo.md, "
            "relativo à raiz do vault."
        )
    posix = to_posix(rel_path.strip())
    candidate_parts = PurePosixPath(posix).parts
    if any(part in _UNSAFE_PARTS or part == ".." for part in candidate_parts):
        raise PathEscapeError(
            f"Caminho {rel_path!r} contém '..' ou segmentos inválidos. "
            "Use apenas caminhos relativos dentro do vault."
        )
    raw = Path(rel_path)
    if raw.is_absolute() or posix.startswith("/") or (len(posix) > 1 and posix[1] == ":"):
        raise PathEscapeError(
            f"Caminho absoluto rejeitado: {rel_path!r}. "
            "Passe um caminho relativo ao vault, por exemplo Projetos/Nix.md."
        )

    root = vault_root.resolve()
    target = (root / Path(*candidate_parts))
    if follow_symlinks:
        resolved = target.resolve()
    else:
        resolved = target.parent.resolve() / target.name
        if target.exists() and target.is_symlink():
            link_target = target.resolve()
            if not _is_relative_to(link_target, root):
                raise PathEscapeError(
                    f"{rel_path!r} é um link simbólico que aponta para fora do vault. "
                    "Remova o symlink ou ative vault.follow_symlinks apenas se for intencional."
                )
            resolved = link_target

    if not _is_relative_to(resolved.resolve() if follow_symlinks else resolved, root):
        raise PathEscapeError(
            f"O caminho {rel_path!r} escapa do vault {root}. "
            "Operações de arquivo são confinadas ao diretório configurado."
        )
    return resolved


def rel_to_vault(vault_root: Path, path: Path) -> str:
    root = vault_root.resolve()
    resolved = path.resolve()
    if not _is_relative_to(resolved, root):
        raise PathEscapeError(
            f"{path} está fora do vault {root}. Use apenas arquivos do vault."
        )
    return resolved.relative_to(root).as_posix()
