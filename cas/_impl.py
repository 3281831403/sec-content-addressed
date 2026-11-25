"""Content-addressed backup store implementation."""

import hashlib

CHUNK_DOMAIN = b"GSB-CAS-CHUNK-V1"
ROOT_DOMAIN = b"GSB-CAS-ROOT-V1"
EMPTY_ROOT = hashlib.sha256(b"GSB-CAS-EMPTY-ROOT-V1").hexdigest()
DEFAULT_CHUNK_SIZE = 8


def chunk_digest(block):
    """Domain-separated digest binding both block length and bytes."""
    return hashlib.sha256(
        CHUNK_DOMAIN + len(block).to_bytes(8, "big") + block
    ).hexdigest()


def root_digest(digests):
    """Bind each digest's length and content, in the supplied order."""
    if not digests:
        return EMPTY_ROOT

    digest = hashlib.sha256()
    digest.update(ROOT_DOMAIN)
    for item in digests:
        raw = item.encode("ascii")
        digest.update(len(raw).to_bytes(4, "big"))
        digest.update(raw)
    return digest.hexdigest()


def put(store, data):
    """Store fixed-size blocks while deduplicating identical chunk content."""
    chunks = store.setdefault("chunks", {})
    objects = store.setdefault("objects", {})

    blocks = chunk(data, DEFAULT_CHUNK_SIZE)
    digests = [chunk_digest(block) for block in blocks]
    lengths = [len(block) for block in blocks]
    root = root_digest(digests)

    for block, digest in zip(blocks, digests):
        entry = chunks.get(digest)
        if entry is None:
            chunks[digest] = {"data": block, "refs": 1}
        else:
            entry["refs"] += 1

    obj = objects.get(root)
    if obj is None:
        objects[root] = {
            "digests": digests,
            "lengths": lengths,
            "size": len(data),
            "refs": 1,
        }
        refs = 1
    else:
        obj["refs"] += 1
        refs = obj["refs"]

    return {"root": root, "refs": refs, "size": len(data)}


def get(store, root):
    """Return data only after every chunk and the ordered root verify."""
    report = verify(store, root)
    if not report["ok"]:
        raise ValueError(f"CAS verification failed at chunk {report['bad_index']}")

    obj = store["objects"][root]
    return b"".join(
        store["chunks"][digest]["data"] for digest in obj["digests"]
    )


def verify(store, root):
    """Return integrity status and stop at the first corrupted chunk."""
    obj = store["objects"][root]
    chunks = store.get("chunks", {})

    for index, expected_digest in enumerate(obj["digests"]):
        entry = chunks.get(expected_digest)
        if entry is None:
            return {"ok": False, "bad_index": index}

        data = entry.get("data")
        if not isinstance(data, (bytes, bytearray)):
            return {"ok": False, "bad_index": index}

        if chunk_digest(bytes(data)) != expected_digest:
            return {"ok": False, "bad_index": index}

    if root_digest(obj["digests"]) != root:
        return {"ok": False, "bad_index": None}

    return {"ok": True, "bad_index": None}


def drop(store, root):
    """Release one object reference; delete content only at zero references."""
    obj = store["objects"][root]
    obj["refs"] -= 1
    remaining = obj["refs"]

    chunks = store["chunks"]
    for digest in obj["digests"]:
        entry = chunks.get(digest)
        if entry is None:
            continue

        entry["refs"] -= 1
        if entry["refs"] <= 0:
            del chunks[digest]

    if remaining > 0:
        return remaining

    del store["objects"][root]
    return 0


def chunk(data, size):
    """Split data into blocks of at most size, retaining a short final block."""
    if size <= 0:
        raise ValueError("chunk size must be a positive integer")

    return [data[start : start + size] for start in range(0, len(data), size)]


def cas_batch(ops, policy):
    """Execute operations against their own supplied stores and cursors."""
    policy = policy or {}
    stop_on_error = bool(policy.get("stop_on_error", False))

    results = []
    errors = []

    for index, op in enumerate(ops):
        op_name = op["op"]
        op_store = op["store"]

        try:
            if op_name == "put":
                result = put(op_store, op["data"])
            elif op_name == "get":
                result = get(op_store, op["root"])
            elif op_name == "verify":
                result = verify(op_store, op["root"])
            elif op_name == "drop":
                result = drop(op_store, op["root"])
            else:
                raise ValueError(f"unknown CAS operation: {op_name!r}")
        except Exception as exc:  # Batch policy records and optionally stops.
            errors.append({"index": index, "op": op_name, "error": str(exc)})
            results.append(None)
            if stop_on_error:
                break
        else:
            results.append(result)

    return {"results": results, "errors": errors}
