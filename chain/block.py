"""Blocks and proof of work bound to the transaction set."""

from __future__ import annotations

from chain.constants import (
    GENESIS_PREVIOUS_HASH,
    MAX_FUTURE_DRIFT_SECONDS,
    MAX_PROOF,
)
from chain.encoding import canonical, sha256_hex
from chain.errors import ChainError

_BLOCK_KEYS = {"index", "timestamp", "transactions", "proof", "previous_hash", "difficulty"}
_HASH_RE_LENGTH = 64


def genesis_block(difficulty: int) -> dict:
    return {
        "index": 0,
        "timestamp": 0,
        "transactions": [],
        "proof": 0,
        "previous_hash": GENESIS_PREVIOUS_HASH,
        "difficulty": difficulty,
    }


def block_hash(block: dict) -> str:
    header = {
        "index": block["index"],
        "timestamp": block["timestamp"],
        "previous_hash": block["previous_hash"],
        "transactions_hash": sha256_hex(canonical(block["transactions"])),
        "proof": block["proof"],
        "difficulty": block["difficulty"],
    }
    return sha256_hex(canonical(header))


def mine_proof(block: dict) -> dict:
    """Find a proof whose header hash has `difficulty` leading zero nibbles."""
    difficulty = block["difficulty"]
    prefix = "0" * difficulty
    for proof in range(MAX_PROOF + 1):
        block["proof"] = proof
        if block_hash(block).startswith(prefix):
            return block
    raise ChainError("proof of work exceeded the search cap")


def require_block_shape(block: dict, *, difficulty: int) -> None:
    if not isinstance(block, dict) or set(block) != _BLOCK_KEYS:
        raise ChainError("block fields are invalid")
    index = _require_int("index", block["index"], minimum=0)
    timestamp = _require_int("timestamp", block["timestamp"], minimum=0)
    proof = _require_int("proof", block["proof"], minimum=0, maximum=MAX_PROOF)
    if block["difficulty"] != difficulty:
        raise ChainError("block difficulty does not match this node")
    previous = block["previous_hash"]
    if not isinstance(previous, str) or len(previous) != _HASH_RE_LENGTH:
        raise ChainError("previous hash is invalid")
    try:
        bytes.fromhex(previous)
    except ValueError as err:
        raise ChainError("previous hash is invalid") from err
    if previous != previous.lower():
        raise ChainError("previous hash is invalid")
    if not isinstance(block["transactions"], list):
        raise ChainError("transactions must be a list")
    # Rebind so later hashing sees the validated integers, not duplicates.
    block["index"] = index
    block["timestamp"] = timestamp
    block["proof"] = proof


def proof_is_valid(block: dict) -> bool:
    return block_hash(block).startswith("0" * block["difficulty"])


def timestamp_is_plausible(timestamp: int, parent_timestamp: int, now: int) -> None:
    if timestamp < parent_timestamp:
        raise ChainError("block timestamp moved backwards")
    if timestamp > now + MAX_FUTURE_DRIFT_SECONDS:
        raise ChainError("block timestamp is too far in the future")


def _require_int(name: str, value: object, *, minimum: int, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ChainError(f"{name} must be an integer")
    if value < minimum or (maximum is not None and value > maximum):
        raise ChainError(f"{name} is out of range")
    return value
