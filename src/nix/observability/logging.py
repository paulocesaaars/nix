"""Logging estruturado em arquivo."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nix.config.schema import NixConfig

_CONFIGURED = False
_LOG_PATH: Path | None = None
_FILE_HANDLER = "nix.file"
_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"(?i)(api[_-]?key\s*[=:]\s*)\S+"),
]


class RedactingFilter(logging.Filter):
    """Remove chaves de API de mensagens e argumentos de log."""

    def __init__(self, extra_secrets: list[str] | None = None) -> None:
        super().__init__()
        self._extras = [s for s in (extra_secrets or []) if s and len(s) >= 8]

    def _redact(self, text: str) -> str:
        for secret in self._extras:
            text = text.replace(secret, "********")
        for pattern in _SECRET_PATTERNS:
            text = pattern.sub("********", text)
        return text

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self._redact(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: self._redact(v) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            else:
                record.args = tuple(
                    self._redact(a) if isinstance(a, str) else a for a in record.args
                )
        if record.exc_text:
            record.exc_text = self._redact(record.exc_text)
        return True


def configure_logging(config: NixConfig, *, extra_secrets: list[str] | None = None) -> logging.Logger:
    """Configura o logger raiz `nix` para o arquivo (stdout no stdio é do protocolo)."""
    global _CONFIGURED, _LOG_PATH
    logger = logging.getLogger("nix")
    logger.setLevel(getattr(logging, config.logging.level.upper(), logging.INFO))
    logger.propagate = False
    log_path = config.logging.file_path.resolve()
    redactor = RedactingFilter(list(extra_secrets or []))
    if _CONFIGURED:
        if _LOG_PATH is None or not _same_path(_LOG_PATH, log_path):
            _retarget(logger, log_path, redactor)
            _retarget(logging.getLogger(), log_path, redactor)
            _LOG_PATH = log_path
        return logger

    handler = _file_handler(log_path, redactor)
    logger.addHandler(handler)

    root = logging.getLogger()
    root.addFilter(redactor)
    if not any(isinstance(existing, logging.FileHandler) for existing in root.handlers):
        root.addHandler(_file_handler(log_path, redactor))
        if root.level == logging.WARNING or root.level == logging.NOTSET:
            root.setLevel(logging.WARNING)
    for lib in ("httpx", "httpcore", "chromadb", "fastembed", "huggingface_hub", "onnxruntime"):
        logging.getLogger(lib).addFilter(redactor)

    _LOG_PATH = log_path
    _CONFIGURED = True
    return logger


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(str(left)) == os.path.normcase(str(right))


def _file_handler(path: Path, redactor: RedactingFilter) -> logging.FileHandler:
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.set_name(_FILE_HANDLER)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    handler.addFilter(redactor)
    return handler


def _retarget(target: logging.Logger, path: Path, redactor: RedactingFilter) -> None:
    owned = [handler for handler in target.handlers if handler.name == _FILE_HANDLER]
    if not owned:
        return
    for handler in owned:
        target.removeHandler(handler)
        handler.close()
    target.addHandler(_file_handler(path, redactor))


def get_logger(name: str = "nix") -> logging.Logger:
    return logging.getLogger(name)
