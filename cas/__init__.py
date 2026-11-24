"""Facade package for the content-addressed backup store exercise."""

from .api import (
    cas_batch,
    chunk,
    chunk_digest,
    drop,
    get,
    put,
    root_digest,
    verify,
)

__all__ = [
    "chunk",
    "chunk_digest",
    "root_digest",
    "put",
    "get",
    "verify",
    "drop",
    "cas_batch",
]