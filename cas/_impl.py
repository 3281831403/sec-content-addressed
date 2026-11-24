"""Content-addressed backup store contracts; every function is a stub."""

import hashlib

CHUNK_DOMAIN = b"GSB-CAS-CHUNK-V1"
ROOT_DOMAIN = b"GSB-CAS-ROOT-V1"
EMPTY_ROOT = hashlib.sha256(b"GSB-CAS-EMPTY-ROOT-V1").hexdigest()
DEFAULT_CHUNK_SIZE = 8


def chunk(data, size):
    """Split data into blocks of at most size; keep the short final block as is."""
    raise NotImplementedError


def chunk_digest(block):
    """Return a domain-separated digest that binds the block length and bytes."""
    raise NotImplementedError


def root_digest(digests):
    """Combine chunk digests in order; an empty input yields EMPTY_ROOT."""
    raise NotImplementedError


def put(store, data):
    """Store data in DEFAULT_CHUNK_SIZE blocks, deduplicating identical content."""
    raise NotImplementedError


def get(store, root):
    """Reassemble an object after checking every chunk and the ordered root."""
    raise NotImplementedError


def verify(store, root):
    """Return whether the object is intact and the first corrupted chunk index."""
    raise NotImplementedError


def drop(store, root):
    """Drop one reference and remove content only when the count reaches zero."""
    raise NotImplementedError


def cas_batch(ops, policy):
    """Run independent CAS operations without sharing a store cursor."""
    raise NotImplementedError