"""Isola stdout de bibliotecas para não corromper o protocolo MCP."""

from __future__ import annotations

import contextlib
import io
import logging
import os
import warnings
from collections.abc import Iterator

logger = logging.getLogger("nix.stdio")


def silence_progress_env() -> None:
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    os.environ.setdefault("TQDM_DISABLE", "1")
    warnings.filterwarnings(
        "ignore",
        message=r"Cannot enable progress bars:.*",
        category=UserWarning,
    )


@contextlib.contextmanager
def capture_library_stdout() -> Iterator[None]:
    """Redireciona prints de bibliotecas para o log, preservando stdout do MCP."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        yield
    text = buf.getvalue()
    if text.strip():
        logger.debug("%s", text.strip())
