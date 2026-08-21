"""Logging estruturado em arquivo."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from nix.config.schema import NixConfig
from nix.observability.stdio import silence_progress_env

_CONFIGURED = False
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
    global _CONFIGURED
    silence_progress_env()
    logger = logging.getLogger("nix")
    logger.setLevel(getattr(logging, config.logging.level.upper(), logging.INFO))
    logger.propagate = False

    redactor = RedactingFilter(list(extra_secrets or []))

    if _CONFIGURED:
        for handler in logger.handlers:
            handler.addFilter(redactor)
        return logger

    log_path: Path = config.logging.file_path
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    handler.addFilter(redactor)
    logger.addHandler(handler)

    root = logging.getLogger()
    root.addFilter(redactor)
    if not any(isinstance(h, logging.FileHandler) for h in root.handlers):
        root_handler = logging.FileHandler(log_path, encoding="utf-8")
        root_handler.setFormatter(handler.formatter)
        root_handler.addFilter(redactor)
        root.addHandler(root_handler)
        if root.level == logging.WARNING or root.level == logging.NOTSET:
            root.setLevel(logging.WARNING)
    for lib in ("httpx", "httpcore", "chromadb", "fastembed", "huggingface_hub", "onnxruntime"):
        lib_logger = logging.getLogger(lib)
        lib_logger.addFilter(redactor)

    _CONFIGURED = True
    return logger


def get_logger(name: str = "nix") -> logging.Logger:
    return logging.getLogger(name)
