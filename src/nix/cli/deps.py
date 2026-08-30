"""Helpers da CLI: runtime e tratamento de erros."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

import typer

from nix.config.loader import load_config
from nix.core.errors import NixError
from nix.core.runtime import Runtime

F = TypeVar("F", bound=Callable[..., Any])


def get_runtime(*, capture_embedder_stdout: bool = True) -> Runtime:
    config = load_config()
    return Runtime.from_config(config, capture_embedder_stdout=capture_embedder_stdout)


def with_errors(fn: F) -> F:
    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except NixError as exc:
            from nix.cli.render import print_error

            print_error(exc.message)
            raise typer.Exit(code=1) from exc

    return wrapper  # type: ignore[return-value]
