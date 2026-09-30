"""Chain state: balances, nonces, mempool, and longest valid chain."""

from __future__ import annotations

import copy
import json
import re
import threading
import time
from pathlib import Path

from chain.block import (
    block_hash,
    genesis_block,
    mine_proof,
    proof_is_valid,
    require_block_shape,
    timestamp_is_plausible,
)
from chain.constants import (
    ADDRESS_LENGTH,
    BLOCK_REWARD,
    DEFAULT_DIFFICULTY,
    FILE_VERSION,
    MAX_CHAIN_LENGTH,
    MAX_DIFFICULTY,
    MAX_MEMPOOL,
    MAX_PEERS,
    MAX_TX_PER_BLOCK,
    MIN_DIFFICULTY,
)
from chain.errors import ChainError
from chain.peers import fetch_chain, normalize_origin
from chain.storage import atomic_write_text
from chain.transaction import (
    apply_block_transactions,
    apply_user_tx,
    coinbase_tx,
    normalize_user_tx,
)

_ADDRESS = re.compile(rf"^[0-9a-f]{{{ADDRESS_LENGTH}}}$")


class Blockchain:
    def __init__(
        self,
        difficulty: int = DEFAULT_DIFFICULTY,
        chain: list | None = None,
        store_path: Path | None = None,
    ):
        if isinstance(difficulty, bool) or not isinstance(difficulty, int):
            raise ChainError("difficulty must be an integer")
        if not MIN_DIFFICULTY <= difficulty <= MAX_DIFFICULTY:
            raise ChainError(
                f"difficulty must be between {MIN_DIFFICULTY} and {MAX_DIFFICULTY}"
            )
        self.difficulty = difficulty
        self.store_path = store_path
        self.mempool: list[dict] = []
        self.peers: set[str] = set()
        self._lock = threading.Lock()
        if chain is None:
            self.chain = [genesis_block(difficulty)]
        else:
            self.chain = copy.deepcopy(chain)
        validate_chain(self.chain, self.difficulty)

    @classmethod
    def from_disk(cls, path: Path, difficulty: int) -> Blockchain:
        if not path.exists():
            return cls(difficulty=difficulty, store_path=path)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as err:
            raise ChainError("chain file is unreadable") from err
        if not isinstance(raw, dict) or raw.get("version") != FILE_VERSION:
            raise ChainError("unsupported chain file version")
        if raw.get("difficulty") != difficulty:
            raise ChainError("saved difficulty does not match CHAIN_DIFFICULTY")
        chain = raw.get("chain")
        if not isinstance(chain, list):
            raise ChainError("chain file is missing a chain")
        node = cls(difficulty=difficulty, chain=chain, store_path=path)
        peers = raw.get("peers", [])
        mempool = raw.get("mempool", [])
        if not isinstance(peers, list) or not isinstance(mempool, list):
            raise ChainError("chain file has an unexpected shape")
        for peer in peers:
            try:
                node.add_peer(peer)
            except ChainError:
                continue
        for tx in mempool:
            try:
                node.add_transaction(tx)
            except ChainError:
                continue
        return node

    def add_transaction(self, raw: dict) -> int:
        with self._lock:
            self._accept(raw)
            self._persist()
            return len(self.chain)

    def add_peer(self, url: str) -> str:
        origin = normalize_origin(url)
        with self._lock:
            if len(self.peers) >= MAX_PEERS and origin not in self.peers:
                raise ChainError("peer list is full")
            self.peers.add(origin)
            self._persist()
            return origin

    def mine(self, miner: str) -> dict:
        if not isinstance(miner, str) or not _ADDRESS.fullmatch(miner):
            raise ChainError("miner address is invalid")
        with self._lock:
            balances, nonces = self._confirmed_state()
            selected, fees = self._select(balances, nonces)
            parent = self.chain[-1]
            timestamp = max(int(time.time()), parent["timestamp"])
            block = {
                "index": len(self.chain),
                "timestamp": timestamp,
                "transactions": [coinbase_tx(miner, BLOCK_REWARD + fees), *copy.deepcopy(selected)],
                "proof": 0,
                "previous_hash": block_hash(parent),
                "difficulty": self.difficulty,
            }
            mine_proof(block)
            validate_chain([*self.chain, block], self.difficulty)
            self.chain.append(block)
            included = {(tx["sender"], tx["nonce"]) for tx in selected}
            self.mempool = [
                tx for tx in self.mempool if (tx["sender"], tx["nonce"]) not in included
            ]
            self._drop_invalid_mempool()
            self._persist()
            return copy.deepcopy(block)

    def adopt_chain_if_longer(self, remote: list) -> bool:
        with self._lock:
            if not isinstance(remote, list) or len(remote) <= len(self.chain):
                return False
            candidate = copy.deepcopy(remote)
            try:
                validate_chain(candidate, self.difficulty)
            except ChainError:
                return False
            self.chain = candidate
            self._drop_invalid_mempool()
            self._persist()
            return True

    def resolve(self, fetcher=fetch_chain) -> bool:
        with self._lock:
            peers = sorted(self.peers)
        candidates = []
        for peer in peers:
            remote = fetcher(peer)
            if isinstance(remote, list):
                candidates.append(remote)
        candidates.sort(key=len, reverse=True)
        for remote in candidates:
            if self.adopt_chain_if_longer(remote):
                return True
        return False

    def balance_of(self, address: str) -> int:
        with self._lock:
            balances, _ = self._confirmed_state()
            return balances.get(address, 0)

    def balances(self) -> dict[str, int]:
        with self._lock:
            balances, _ = self._confirmed_state()
            return dict(balances)

    def confirmed_nonce(self, address: str) -> int:
        with self._lock:
            _, nonces = self._confirmed_state()
            return nonces.get(address, 0)

    def next_nonce(self, address: str) -> int:
        with self._lock:
            _, nonces = self._confirmed_state()
            nonce = nonces.get(address, 0)
            pending = sorted(tx["nonce"] for tx in self.mempool if tx["sender"] == address)
            for queued in pending:
                if queued == nonce:
                    nonce += 1
                elif queued > nonce:
                    break
            return nonce

    def chain_copy(self) -> list:
        with self._lock:
            return copy.deepcopy(self.chain)

    def mempool_copy(self) -> list:
        with self._lock:
            return copy.deepcopy(self.mempool)

    def peer_list(self) -> list[str]:
        with self._lock:
            return sorted(self.peers)

    def _accept(self, raw: dict) -> None:
        tx = normalize_user_tx(raw)
        if any(
            existing["sender"] == tx["sender"] and existing["nonce"] == tx["nonce"]
            for existing in self.mempool
        ):
            raise ChainError("transaction nonce is already queued")
        if len(self.mempool) >= MAX_MEMPOOL:
            raise ChainError("mempool is full")
        balances, nonces = self._confirmed_state()
        self._apply_mempool(balances, nonces)
        apply_user_tx(tx, balances, nonces)
        self.mempool.append(tx)

    def _apply_mempool(self, balances: dict[str, int], nonces: dict[str, int]) -> None:
        ordered = sorted(self.mempool, key=lambda tx: (tx["sender"], tx["nonce"]))
        for tx in ordered:
            apply_user_tx(tx, balances, nonces)

    def _select(self, balances: dict[str, int], nonces: dict[str, int]) -> tuple[list[dict], int]:
        grouped: dict[str, list[dict]] = {}
        for tx in self.mempool:
            grouped.setdefault(tx["sender"], []).append(tx)
        selected: list[dict] = []
        fees = 0
        scratch_balances = dict(balances)
        scratch_nonces = dict(nonces)
        room = MAX_TX_PER_BLOCK - 1
        for sender in sorted(grouped):
            for tx in sorted(grouped[sender], key=lambda item: item["nonce"]):
                if len(selected) >= room:
                    return selected, fees
                try:
                    normalize_user_tx(tx)
                    fees += apply_user_tx(tx, scratch_balances, scratch_nonces)
                except ChainError:
                    break
                selected.append(tx)
        return selected, fees

    def _drop_invalid_mempool(self) -> None:
        queued = list(self.mempool)
        self.mempool = []
        for tx in queued:
            try:
                self._accept(tx)
            except ChainError:
                continue

    def _confirmed_state(self) -> tuple[dict[str, int], dict[str, int]]:
        return validate_chain(self.chain, self.difficulty)

    def _persist(self) -> None:
        if self.store_path is None:
            return
        payload = {
            "version": FILE_VERSION,
            "difficulty": self.difficulty,
            "chain": self.chain,
            "mempool": self.mempool,
            "peers": sorted(self.peers),
        }
        atomic_write_text(self.store_path, json.dumps(payload, indent=2) + "\n")


def validate_chain(
    chain: list,
    difficulty: int,
    *,
    now: int | None = None,
) -> tuple[dict[str, int], dict[str, int]]:
    if now is None:
        now = int(time.time())
    if not isinstance(chain, list) or not chain:
        raise ChainError("chain is empty")
    if len(chain) > MAX_CHAIN_LENGTH:
        raise ChainError("chain is too long")
    balances: dict[str, int] = {}
    nonces: dict[str, int] = {}
    previous_hash = None
    parent_timestamp = 0
    for index, block in enumerate(chain):
        if not isinstance(block, dict):
            raise ChainError("block fields are invalid")
        require_block_shape(block, difficulty=difficulty)
        if block["index"] != index:
            raise ChainError("block index does not match its position")
        if index == 0:
            if block != genesis_block(difficulty):
                raise ChainError("genesis block does not match")
        else:
            if block["previous_hash"] != previous_hash:
                raise ChainError("previous hash does not match")
            timestamp_is_plausible(block["timestamp"], parent_timestamp, now)
            if not proof_is_valid(block):
                raise ChainError("proof of work is invalid")
            apply_block_transactions(block["transactions"], balances, nonces)
        previous_hash = block_hash(block)
        parent_timestamp = block["timestamp"]
    return balances, nonces
