"""Registra e remove NIX_HOME e o comando `nix` no PATH do usuário."""

from __future__ import annotations

import contextlib
import os
import shlex
import shutil
import sys
from collections.abc import Callable
from pathlib import Path

_MARKER_BEGIN = "# >>> nix >>>"
_MARKER_END = "# <<< nix <<<"
_WINDOWS_PATH_ENTRY = r"%NIX_HOME%\bin"


def to_posix(path: Path) -> str:
    """Caminho no estilo POSIX (`/c/Git/nix` no Git Bash)."""
    raw = str(path)
    with contextlib.suppress(OSError):
        raw = str(path.resolve())
    raw = raw.replace("\\", "/")
    if len(raw) >= 2 and raw[1] == ":":
        return f"/{raw[0].lower()}{raw[2:]}"
    return raw


def _unix_env_block(root: Path) -> str:
    quoted = shlex.quote(to_posix(root))
    return (
        f"{_MARKER_BEGIN}\n"
        f"export NIX_HOME={quoted}\n"
        f'case ":$PATH:" in *":$NIX_HOME/bin:"*) ;; *) export PATH="$NIX_HOME/bin:$PATH" ;; esac\n'
        f"{_MARKER_END}\n"
    )


def _strip_partial_markers(text: str) -> str:
    begin = text.find(_MARKER_BEGIN)
    end = text.find(_MARKER_END)
    if begin != -1:
        stripped = text[:begin].rstrip()
        return f"{stripped}\n" if stripped else ""
    if end != -1:
        line_start = text.rfind("\n", 0, end) + 1
        stop = end + len(_MARKER_END)
        if stop < len(text) and text[stop] == "\n":
            stop += 1
        stripped = (text[:line_start] + text[stop:]).rstrip()
        return f"{stripped}\n" if stripped else ""
    return text


def _remove_nix_block(text: str) -> str:
    begin = text.find(_MARKER_BEGIN)
    end = text.find(_MARKER_END)
    if begin != -1 and end != -1 and end > begin:
        stop = end + len(_MARKER_END)
        if stop < len(text) and text[stop] == "\n":
            stop += 1
        stripped = (text[:begin] + text[stop:]).replace("\n\n\n", "\n\n").rstrip()
        return f"{stripped}\n" if stripped else ""
    return _strip_partial_markers(text)


def _root_path_tokens(root: Path) -> set[str]:
    candidates = [root]
    with contextlib.suppress(OSError):
        candidates.append(root.resolve())
    tokens: set[str] = set()
    for path in candidates:
        tokens.add(to_posix(path).rstrip("/").casefold())
        tokens.add(str(path).replace("\\", "/").rstrip("/").casefold())
    return tokens


def _same_install_root(left: Path, right: Path) -> bool:
    return bool(_root_path_tokens(left) & _root_path_tokens(right))


def _block_nix_home(text: str) -> str | None:
    begin = text.find(_MARKER_BEGIN)
    end = text.find(_MARKER_END)
    if begin == -1 or end == -1 or end <= begin:
        return None
    for line in text[begin:end].splitlines():
        stripped = line.strip()
        if stripped.startswith("export NIX_HOME="):
            return stripped.split("=", 1)[1].strip().strip("'").strip('"')
    return None


def _block_belongs_to(text: str, root: Path) -> bool:
    begin = text.find(_MARKER_BEGIN)
    end = text.find(_MARKER_END)
    if begin == -1 and end == -1:
        return False
    home = _block_nix_home(text)
    if home is None:
        return True
    return home.replace("\\", "/").rstrip("/").casefold() in _root_path_tokens(root)


def _upsert_rc_block(path: Path, block: str) -> None:
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    begin = text.find(_MARKER_BEGIN)
    end = text.find(_MARKER_END)
    if begin != -1 and end != -1 and end > begin:
        stop = end + len(_MARKER_END)
        if stop < len(text) and text[stop] == "\n":
            stop += 1
        text = text[:begin] + block + text[stop:]
    else:
        text = _strip_partial_markers(text)
        if text and not text.endswith("\n"):
            text += "\n"
        if text:
            text += "\n"
        text += block
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _windows_broadcast_env() -> None:
    import ctypes
    from ctypes import wintypes

    hwnd_broadcast = 0xFFFF
    wm_settingchange = 0x001A
    smto_abortifhung = 0x0002
    result = wintypes.DWORD()
    send = ctypes.windll.user32.SendMessageTimeoutW
    send.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPCWSTR,
        wintypes.UINT,
        wintypes.UINT,
        ctypes.POINTER(wintypes.DWORD),
    ]
    send.restype = ctypes.c_void_p
    send(
        hwnd_broadcast,
        wm_settingchange,
        0,
        "Environment",
        smto_abortifhung,
        5000,
        ctypes.byref(result),
    )


def _windows_set_user_env(name: str, value: str, *, expand: bool) -> None:
    import winreg

    kind = winreg.REG_EXPAND_SZ if expand else winreg.REG_SZ
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ | winreg.KEY_WRITE)
    try:
        winreg.SetValueEx(key, name, 0, kind, value)
    finally:
        key.Close()


def _path_already_has_nix_bin(user_path: str, bin_dir: Path) -> bool:
    wanted = str(bin_dir).rstrip("\\/").casefold()
    posix_wanted = to_posix(bin_dir).rstrip("/").casefold()
    aliases = {_WINDOWS_PATH_ENTRY.casefold(), r"%NIX_HOME%/bin".casefold()}
    for raw in user_path.split(";"):
        token = raw.strip().strip('"')
        if not token:
            continue
        normalized = token.replace("/", "\\").rstrip("\\").casefold()
        if normalized in aliases:
            return True
        expanded = os.path.expandvars(token).rstrip("\\/")
        if expanded.casefold() == wanted:
            return True
        if expanded.replace("\\", "/").rstrip("/").casefold() == posix_wanted:
            return True
    return False


def _windows_append_user_path(bin_dir: Path) -> None:
    import winreg

    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ | winreg.KEY_WRITE)
    try:
        try:
            current, _kind = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            current = ""
        if not isinstance(current, str):
            current = str(current)
        if _path_already_has_nix_bin(current, bin_dir):
            return
        updated = _WINDOWS_PATH_ENTRY if not current.strip() else current.rstrip(";") + ";" + _WINDOWS_PATH_ENTRY
        winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, updated)
    finally:
        key.Close()


def _windows_get_user_env(name: str) -> str | None:
    import winreg

    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ)
    except FileNotFoundError:
        return None
    try:
        value, _kind = winreg.QueryValueEx(key, name)
    except FileNotFoundError:
        return None
    finally:
        key.Close()
    if not isinstance(value, str):
        return str(value) if value is not None else None
    return value


def _windows_delete_user_env(name: str) -> None:
    import winreg

    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ | winreg.KEY_WRITE)
    except FileNotFoundError:
        return
    try:
        winreg.DeleteValue(key, name)
    except FileNotFoundError:
        return
    finally:
        key.Close()


def _windows_path_token_is_ours(token: str, bin_dir: Path, *, remove_expand_entry: bool) -> bool:
    wanted = str(bin_dir).rstrip("\\/").casefold()
    posix_wanted = to_posix(bin_dir).rstrip("/").casefold()
    aliases = {_WINDOWS_PATH_ENTRY.casefold(), r"%NIX_HOME%/bin".casefold()}
    normalized = token.replace("/", "\\").rstrip("\\").casefold()
    if remove_expand_entry and normalized in aliases:
        return True
    expanded = os.path.expandvars(token).rstrip("\\/")
    if expanded.casefold() == wanted:
        return True
    return expanded.replace("\\", "/").rstrip("/").casefold() == posix_wanted


def _windows_remove_user_path(bin_dir: Path, *, remove_expand_entry: bool) -> None:
    import winreg

    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ | winreg.KEY_WRITE)
    except FileNotFoundError:
        return
    try:
        try:
            current, kind = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            return
        if not isinstance(current, str):
            current = str(current)
        kept: list[str] = []
        for raw in current.split(";"):
            token = raw.strip().strip('"')
            if not token:
                continue
            if _windows_path_token_is_ours(token, bin_dir, remove_expand_entry=remove_expand_entry):
                continue
            kept.append(raw)
        updated = ";".join(kept)
        if updated == current:
            return
        winreg.SetValueEx(key, "Path", 0, kind, updated)
    finally:
        key.Close()


def _fail(message: str, code: int = 1) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(code)


def print_manual_env_help(root: Path, failures: list[str]) -> None:
    """Aponta para o INSTALL.md; não duplica o passo a passo."""
    bin_dir = root / "bin"
    windows = any(item.startswith("Windows") for item in failures)
    unix = any(item.startswith("shell") for item in failures)
    if windows and not unix:
        guide = 'Siga o INSTALL.md, seções Windows (interface ou PowerShell).'
    elif unix and not windows:
        guide = 'Siga o INSTALL.md, seção "Linux, macOS e Git Bash".'
    else:
        guide = 'Siga o INSTALL.md, seção "Registrar NIX_HOME e o PATH à mão".'
    print(
        "[erro] Não foi possível registrar NIX_HOME e o PATH automaticamente.\n"
        f"  NIX_HOME={root}\n"
        f"  bin={bin_dir}\n"
        f"{guide}",
        file=sys.stderr,
    )


def print_manual_unenv_help(root: Path, failures: list[str]) -> None:
    """Aponta para o INSTALL.md na remoção manual do PATH."""
    bin_dir = root / "bin"
    windows = any(item.startswith("Windows") for item in failures)
    unix = any(item.startswith("shell") for item in failures)
    if windows and not unix:
        guide = 'Siga o INSTALL.md, seção "Remover NIX_HOME e o PATH à mão" (Windows).'
    elif unix and not windows:
        guide = 'Siga o INSTALL.md, seção "Remover NIX_HOME e o PATH à mão" (Linux, macOS e Git Bash).'
    else:
        guide = 'Siga o INSTALL.md, seção "Remover NIX_HOME e o PATH à mão".'
    print(
        "[erro] Não foi possível remover NIX_HOME e o PATH automaticamente.\n"
        f"  NIX_HOME={root}\n"
        f"  bin={bin_dir}\n"
        f"{guide}",
        file=sys.stderr,
    )


def _register_windows(root: Path) -> None:
    bin_dir = root / "bin"
    _windows_set_user_env("NIX_HOME", str(root), expand=False)
    _windows_append_user_path(bin_dir)
    with contextlib.suppress(OSError, AttributeError):
        _windows_broadcast_env()


def _unix_rc_targets(*, ensure_bashrc: bool) -> list[Path]:
    """Rcs a atualizar: não cria `.profile` do zero; no Unix só anexa arquivos existentes."""
    home = Path.home()
    names = (".bashrc", ".zshrc", ".bash_profile", ".profile")
    targets: list[Path] = []
    seen: set[str] = set()

    def add(path: Path) -> None:
        key = str(path)
        if key in seen:
            return
        seen.add(key)
        targets.append(path)

    if ensure_bashrc:
        add(home / ".bashrc")
        for name in names:
            candidate = home / name
            if candidate.is_file():
                add(candidate)
        return targets

    for name in names:
        candidate = home / name
        if candidate.is_file():
            add(candidate)
    if not targets:
        add(home / ".bashrc")
    return targets


def _register_unix(root: Path, *, ensure_bashrc: bool = False) -> None:
    block = _unix_env_block(root)
    for path in _unix_rc_targets(ensure_bashrc=ensure_bashrc):
        _upsert_rc_block(path, block)


def _unregister_windows(root: Path) -> None:
    stored = _windows_get_user_env("NIX_HOME")
    ours = stored is None or not stored.strip() or _same_install_root(Path(os.path.expandvars(stored)), root)
    if stored and ours:
        _windows_delete_user_env("NIX_HOME")
    _windows_remove_user_path(root / "bin", remove_expand_entry=ours)
    with contextlib.suppress(OSError, AttributeError):
        _windows_broadcast_env()


def _unix_rc_existing() -> list[Path]:
    home = Path.home()
    names = (".bashrc", ".zshrc", ".bash_profile", ".profile")
    return [home / name for name in names if (home / name).is_file()]


def _remove_rc_block_if_ours(path: Path, root: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if not _block_belongs_to(text, root):
        return
    updated = _remove_nix_block(text)
    if updated == text:
        return
    path.write_text(updated, encoding="utf-8")


def _unregister_unix(root: Path) -> None:
    for path in _unix_rc_existing():
        _remove_rc_block_if_ours(path, root)


def _drop_bin_from_process_path(bin_dir: Path) -> None:
    current = os.environ.get("PATH", "")
    if not current:
        return
    wanted = _root_path_tokens(bin_dir)
    kept: list[str] = []
    changed = False
    for raw in current.split(os.pathsep):
        token = raw.strip().strip('"')
        if token and token.replace("\\", "/").rstrip("/").casefold() in wanted:
            changed = True
            continue
        kept.append(raw)
    if changed:
        os.environ["PATH"] = os.pathsep.join(kept)


def _our_bin_names(root: Path) -> set[str]:
    bin_dir = (root / "bin").resolve()
    names = {"nix", "nix.cmd", "nix.exe", "env.sh", "env.cmd", "env.ps1"}
    keys: set[str] = {str(bin_dir).casefold()}
    for name in names:
        keys.add(str((bin_dir / name).resolve()).casefold())
    return keys


def _warn_existing_nix(root: Path) -> None:
    found = shutil.which("nix") or shutil.which("nix.cmd")
    if not found:
        return
    try:
        resolved = str(Path(found).resolve()).casefold()
    except OSError:
        resolved = found.casefold()
    if resolved in _our_bin_names(root):
        return
    ours = root / "bin"
    print(
        f"[aviso] Já existe um comando `nix` em {found}. "
        "Este projeto (Nix MCP) entra na frente do PATH e passa a ser o `nix` do terminal. "
        "Se você usa o gerenciador Nix (NixOS/Nixpkgs), chame-o pelo caminho absoluto "
        f"ou tire {ours} do PATH.",
        file=sys.stderr,
    )


def _try_register(label: str, action: Callable[[], None]) -> str | None:
    try:
        action()
    except OSError as exc:
        return f"{label}: {exc}"
    return None


def register_user_command(root: Path) -> bool:
    """Grava NIX_HOME e coloca `{NIX_HOME}/bin` no PATH do usuário.

    Retorna False se algum alvo permanente falhar; a instalação segue e o
    usuário deve gravar à mão só o que faltou (INSTALL.md).
    """
    bin_dir = root / "bin"
    if not (bin_dir / "nix").is_file() and not (bin_dir / "nix.cmd").is_file():
        _fail(
            f"Não achei os wrappers em {bin_dir}. "
            "Rode o instalador na raiz do repositório Nix."
        )
    _warn_existing_nix(root)
    os.environ["NIX_HOME"] = str(root)
    current_path = os.environ.get("PATH", "")
    prefix = str(bin_dir)
    present = {item.casefold() for item in current_path.split(os.pathsep)}
    if prefix.casefold() not in present:
        os.environ["PATH"] = prefix + os.pathsep + current_path

    failures: list[str] = []
    if os.name == "nt":
        failed = _try_register("Windows (NIX_HOME/PATH)", lambda: _register_windows(root))
        if failed:
            failures.append(failed)
        msystem = bool(os.environ.get("MSYSTEM"))
        has_shell_rc = any(
            (Path.home() / name).is_file()
            for name in (".bashrc", ".profile", ".bash_profile", ".zshrc")
        )
        if msystem or has_shell_rc:
            failed = _try_register(
                "shell (~/.bashrc)",
                lambda: _register_unix(root, ensure_bashrc=msystem),
            )
            if failed:
                failures.append(failed)
    else:
        failed = _try_register("shell (~/.bashrc)", lambda: _register_unix(root))
        if failed:
            failures.append(failed)

    if failures:
        for item in failures:
            print(f"[erro] {item}", file=sys.stderr)
        print_manual_env_help(root, failures)
        return False

    print(f"NIX_HOME={root}")
    print(f"Comando nix: {bin_dir}")
    return True


def unregister_user_command(root: Path) -> bool:
    """Remove NIX_HOME e `{NIX_HOME}/bin` do PATH permanente deste install.

    Só altera a variável e a entrada `%NIX_HOME%\\bin` se apontarem para `root`.
    Retorna False se algum alvo permanente falhar; a desinstalação local segue.
    """
    home = os.environ.get("NIX_HOME", "").strip()
    if home and _same_install_root(Path(home), root):
        os.environ.pop("NIX_HOME", None)
    _drop_bin_from_process_path(root / "bin")

    failures: list[str] = []
    if os.name == "nt":
        failed = _try_register("Windows (NIX_HOME/PATH)", lambda: _unregister_windows(root))
        if failed:
            failures.append(failed)
        msystem = bool(os.environ.get("MSYSTEM"))
        has_shell_rc = any(
            (Path.home() / name).is_file()
            for name in (".bashrc", ".profile", ".bash_profile", ".zshrc")
        )
        if msystem or has_shell_rc:
            failed = _try_register("shell (~/.bashrc)", lambda: _unregister_unix(root))
            if failed:
                failures.append(failed)
    else:
        failed = _try_register("shell (~/.bashrc)", lambda: _unregister_unix(root))
        if failed:
            failures.append(failed)

    if failures:
        for item in failures:
            print(f"[erro] {item}", file=sys.stderr)
        print_manual_unenv_help(root, failures)
        return False

    print("NIX_HOME e o comando nix foram removidos do PATH permanente.")
    return True
