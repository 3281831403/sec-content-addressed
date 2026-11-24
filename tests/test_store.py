import hashlib

import pytest

from cas import (
    cas_batch,
    chunk,
    chunk_digest,
    drop,
    get,
    put,
    root_digest,
    verify,
)


CHUNK_DOMAIN = b"GSB-CAS-CHUNK-V1"
ROOT_DOMAIN = b"GSB-CAS-ROOT-V1"
EMPTY_ROOT = hashlib.sha256(b"GSB-CAS-EMPTY-ROOT-V1").hexdigest()
DEFAULT_CHUNK_SIZE = 8


def _chunk_ref(block):
    return hashlib.sha256(
        CHUNK_DOMAIN + len(block).to_bytes(8, "big") + block
    ).hexdigest()


def _root_ref(digests):
    if not digests:
        return EMPTY_ROOT
    digest = hashlib.sha256()
    digest.update(ROOT_DOMAIN)
    for item in digests:
        raw = item.encode("ascii")
        digest.update(len(raw).to_bytes(4, "big"))
        digest.update(raw)
    return digest.hexdigest()


def _manifest(store, root):
    return list(store["objects"][root]["digests"])


def _corrupt_chunk(store, digest):
    old = store["chunks"][digest]["data"]
    store["chunks"][digest]["data"] = bytes((value + 1) % 256 for value in old)


def test_chunk_digest_binds_length_prefix():
    assert chunk_digest(b"boundary") == _chunk_ref(b"boundary")
    assert chunk_digest(b"") == _chunk_ref(b"")
    assert chunk_digest(b"\x00" * 8) == _chunk_ref(b"\x00" * 8)
    assert chunk_digest(b"boundary") != hashlib.sha256(b"boundary").hexdigest()


def test_root_digest_binds_chunk_digest_content():
    left = [chunk_digest(b"AAAA"), chunk_digest(b"BBBB")]
    right = [chunk_digest(b"CCCC"), chunk_digest(b"DDDD")]

    assert sum(map(len, left)) == sum(map(len, right))
    assert root_digest(left) == _root_ref(left)
    assert root_digest(left) != root_digest(right)


def test_root_digest_binds_chunk_order():
    first = chunk_digest(b"first-block")
    second = chunk_digest(b"second-block")
    forward = [first, second]
    backward = [second, first]

    assert first != second
    assert root_digest(forward) == _root_ref(forward)
    assert root_digest(forward) != root_digest(backward)


def test_empty_root_is_domain_constant():
    only = chunk_digest(b"only-block")

    assert root_digest([]) == EMPTY_ROOT
    assert root_digest([]) != ""
    assert root_digest([]) != only
    assert root_digest([only]) != EMPTY_ROOT


def test_put_deduplicates_identical_content_and_counts_refs():
    store = {}
    data = b"same"

    first = put(store, data)
    root = first["root"]
    chunk_count = len(store["chunks"])
    only_digest = next(iter(store["chunks"]))

    second = put(store, data)

    assert second["root"] == root
    assert second["refs"] == 2
    assert first["refs"] == 1
    assert len(store["chunks"]) == chunk_count == 1
    assert len(store["objects"]) == 1
    assert store["objects"][root]["refs"] == 2
    assert store["chunks"][only_digest]["refs"] == 2


def test_get_rejects_replaced_chunk():
    store = {}
    data = b"AAAABBBBCCCCC"
    root = put(store, data)["root"]
    digests = _manifest(store, root)

    assert len(digests) == 2
    _corrupt_chunk(store, digests[1])

    with pytest.raises(ValueError):
        get(store, root)


def test_verify_reports_first_bad_chunk():
    store = {}
    data = b"0123456789abcdefghij"
    root = put(store, data)["root"]
    digests = _manifest(store, root)

    assert len(digests) == 3
    _corrupt_chunk(store, digests[0])
    _corrupt_chunk(store, digests[2])

    report = verify(store, root)

    assert report["ok"] is False
    assert report["bad_index"] == 0


def test_drop_keeps_content_while_references_remain():
    store = {}
    data = b"retained"
    root = put(store, data)["root"]
    put(store, data)
    digest = _manifest(store, root)[0]

    assert drop(store, root) == 1
    assert store["objects"][root]["refs"] == 1
    assert store["chunks"][digest]["refs"] == 1
    assert get(store, root) == data


def test_chunking_keeps_short_final_block():
    assert chunk(b"", 4) == []
    assert chunk(b"abcd", 4) == [b"abcd"]
    assert chunk(b"abcde", 4) == [b"abcd", b"e"]
    assert chunk(b"abcdefgh", 4) == [b"abcd", b"efgh"]

    blocks = chunk(b"abcdef", 4)

    assert [len(block) for block in blocks] == [4, 2]
    assert blocks[-1] == b"ef"
    assert chunk_digest(blocks[-1]) == _chunk_ref(b"ef")
    assert chunk_digest(blocks[-1]) != _chunk_ref(b"ef\x00\x00")


def test_batch_operations_do_not_share_store_cursor():
    store_a = {}
    store_b = {}
    data_a = b"alpha-data"
    data_b = b"beta-data"

    outcome = cas_batch(
        [
            {"op": "put", "store": store_a, "data": data_a},
            {"op": "put", "store": store_b, "data": data_b},
        ],
        {"stop_on_error": True},
    )

    assert outcome["errors"] == []
    roots = [item["root"] for item in outcome["results"]]

    assert get(store_a, roots[0]) == data_a
    assert get(store_b, roots[1]) == data_b
    assert roots[0] in store_a["objects"]
    assert roots[1] in store_b["objects"]
    assert len(store_a["objects"]) == 1
    assert len(store_b["objects"]) == 1


def test_put_get_roundtrip_is_byte_exact():
    store = {}
    payload = bytes(range(256)) + b"\x00last"

    result = put(store, payload)

    assert result["size"] == len(payload)
    assert get(store, result["root"]) == payload


def test_every_replaced_chunk_detected_with_exact_index():
    payload = bytes(range(43))
    blocks = chunk(payload, DEFAULT_CHUNK_SIZE)

    assert len(blocks) == 6
    assert len(blocks[-1]) == 3

    for index in range(len(blocks)):
        store = {}
        root = put(store, payload)["root"]
        digests = _manifest(store, root)
        assert digests == [chunk_digest(block) for block in blocks]

        _corrupt_chunk(store, digests[index])

        report = verify(store, root)

        assert report["ok"] is False
        assert report["bad_index"] == index
        with pytest.raises(ValueError):
            get(store, root)


def test_shared_chunk_is_stored_once_across_objects():
    store = {}
    prefix = b"COMMON!!"
    data_a = prefix + b"alpha"
    data_b = prefix + b"bravo"
    common = chunk_digest(prefix)

    result_a = put(store, data_a)
    result_b = put(store, data_b)

    assert len(prefix) == DEFAULT_CHUNK_SIZE
    assert result_a["root"] != result_b["root"]
    assert common in store["chunks"]
    assert store["chunks"][common]["refs"] == 2
    assert len(store["chunks"]) == 3
    assert _manifest(store, result_a["root"])[0] == common
    assert _manifest(store, result_b["root"])[0] == common
    assert get(store, result_a["root"]) == data_a
    assert get(store, result_b["root"]) == data_b


def test_drop_removes_content_when_reference_count_reaches_zero():
    store = {}
    data = b"remove-me"
    root = put(store, data)["root"]
    digests = _manifest(store, root)

    assert len(digests) == 2
    assert drop(store, root) == 0
    assert root not in store["objects"]
    assert all(digest not in store["chunks"] for digest in digests)
    assert store["chunks"] == {}

    with pytest.raises(KeyError):
        get(store, root)


def test_independent_batches_match_individual_operations():
    data_a = b"batch-alpha"
    data_b = b"batch-bravo"

    individual_a_store = {}
    individual_b_store = {}
    individual_a = put(individual_a_store, data_a)
    individual_b = put(individual_b_store, data_b)

    batch_a_store = {}
    batch_b_store = {}
    batch_a = cas_batch(
        [{"op": "put", "store": batch_a_store, "data": data_a}],
        {"stop_on_error": False},
    )
    batch_b = cas_batch(
        [{"op": "put", "store": batch_b_store, "data": data_b}],
        {"stop_on_error": False},
    )

    assert batch_a["errors"] == []
    assert batch_b["errors"] == []
    assert batch_a["results"][0]["root"] == individual_a["root"]
    assert batch_b["results"][0]["root"] == individual_b["root"]
    assert get(batch_a_store, individual_a["root"]) == data_a
    assert get(batch_b_store, individual_b["root"]) == data_b
    assert set(batch_a_store["chunks"]) == set(individual_a_store["chunks"])
    assert set(batch_b_store["chunks"]) == set(individual_b_store["chunks"])
    assert batch_a_store["objects"][individual_a["root"]]["refs"] == 1
    assert batch_b_store["objects"][individual_b["root"]]["refs"] == 1