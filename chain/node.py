"""Local HTTP node. State-changing routes are POST and require a custom header."""

from __future__ import annotations

import hmac
import logging
import os
import re
from functools import wraps
from pathlib import Path

from flask import Flask, current_app, jsonify, request

from chain.block import block_hash
from chain.blockchain import Blockchain
from chain.constants import ADDRESS_LENGTH, DEFAULT_DIFFICULTY
from chain.errors import ChainError
from chain.peers import normalize_origin
from chain.wallet import Wallet

_ADDRESS = re.compile(rf"^[0-9a-f]{{{ADDRESS_LENGTH}}}$")
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
log = logging.getLogger("chain.node")


def bind_is_allowed(host: str, token: str) -> bool:
    if host in _LOCAL_HOSTS:
        return True
    return bool(token)


def create_app(
    blockchain: Blockchain | None = None,
    *,
    data_dir: str | Path | None = None,
    api_token: str | None = None,
    difficulty: int | None = None,
) -> Flask:
    data_path = Path(data_dir if data_dir is not None else os.environ.get("CHAIN_DATA_DIR", "data"))
    if api_token is None:
        api_token = os.environ.get("CHAIN_API_TOKEN", "")
    if blockchain is None:
        chosen = _difficulty_from_env() if difficulty is None else difficulty
        blockchain = Blockchain.from_disk(data_path / "chain.json", chosen)
    elif difficulty is not None and blockchain.difficulty != difficulty:
        raise ChainError("difficulty does not match the provided chain")

    wallet = Wallet.load_or_create(data_path / "node_key.json")
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024
    app.config["JSON_SORT_KEYS"] = True
    app.config["API_TOKEN"] = api_token or ""
    app.extensions["chain_wallet"] = wallet
    app.extensions["blockchain"] = blockchain

    def chain() -> Blockchain:
        return current_app.extensions["blockchain"]

    def miner_address() -> str:
        return current_app.extensions["chain_wallet"].address

    @app.after_request
    def _headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/health")
    def health():
        snapshot = chain().chain_copy()
        return jsonify({"status": "ok", "length": len(snapshot), "difficulty": chain().difficulty})

    @app.get("/node")
    def node_info():
        return jsonify({"address": miner_address()})

    @app.get("/chain")
    def full_chain():
        snapshot = chain().chain_copy()
        return jsonify({"chain": snapshot, "length": len(snapshot)})

    @app.get("/mempool")
    def mempool():
        queued = chain().mempool_copy()
        return jsonify({"transactions": queued, "length": len(queued)})

    @app.get("/account/<address>")
    @route_errors
    def account(address: str):
        if not _ADDRESS.fullmatch(address):
            raise ChainError("address is invalid")
        node = chain()
        return jsonify(
            {
                "address": address,
                "balance": node.balance_of(address),
                "nonce": node.confirmed_nonce(address),
                "next_nonce": node.next_nonce(address),
            }
        )

    @app.get("/nodes")
    def nodes():
        peers = chain().peer_list()
        return jsonify({"nodes": peers, "length": len(peers)})

    @app.post("/mine")
    @route_errors
    @require_mutation
    def mine():
        block = chain().mine(miner_address())
        return jsonify(
            {
                "message": "block mined",
                "index": block["index"],
                "transactions": block["transactions"],
                "proof": block["proof"],
                "previous_hash": block["previous_hash"],
                "hash": block_hash(block),
                "miner": miner_address(),
            }
        )

    @app.post("/transactions/new")
    @route_errors
    @require_mutation
    def new_transaction():
        body = _json_body()
        index = chain().add_transaction(body)
        return jsonify({"message": "transaction queued", "block_index": index}), 201

    @app.post("/nodes/register")
    @route_errors
    @require_mutation
    def register_nodes():
        body = _json_body()
        nodes_field = body.get("nodes")
        if not isinstance(nodes_field, list) or not nodes_field:
            raise ChainError("nodes must be a non-empty list")
        if not all(isinstance(item, str) for item in nodes_field):
            raise ChainError("nodes must be a list of urls")
        origins: list[str] = []
        seen: set[str] = set()
        for item in nodes_field:
            origin = normalize_origin(item)
            if origin not in seen:
                seen.add(origin)
                origins.append(origin)
        accepted = [chain().add_peer(origin) for origin in origins]
        return jsonify({"message": "peers registered", "nodes": accepted}), 201

    @app.post("/nodes/resolve")
    @route_errors
    @require_mutation
    def resolve():
        replaced = chain().resolve()
        length = len(chain().chain_copy())
        if replaced:
            log.info("replaced local chain; length=%s", length)
            message = "chain replaced"
        else:
            message = "local chain kept"
        return jsonify({"message": message, "replaced": replaced, "length": length})

    @app.errorhandler(404)
    def not_found(_err):
        return jsonify({"error": "not found"}), 404

    @app.errorhandler(413)
    def too_large(_err):
        return jsonify({"error": "request is too large"}), 413

    return app


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("CHAIN_LOG_LEVEL", "INFO"),
        format="%(levelname)s %(message)s",
    )
    host = os.environ.get("CHAIN_HOST", "127.0.0.1")
    try:
        port = int(os.environ.get("CHAIN_PORT", "5000"))
    except ValueError:
        log.error("CHAIN_PORT must be an integer")
        raise SystemExit(2) from None
    token = os.environ.get("CHAIN_API_TOKEN", "")
    if not bind_is_allowed(host, token):
        log.error("Set CHAIN_API_TOKEN before binding to %s", host)
        raise SystemExit(2)
    try:
        app = create_app()
    except ChainError as err:
        log.error("%s", err)
        raise SystemExit(2) from None
    address = app.extensions["chain_wallet"].address
    log.info("miner %s listening on %s:%s", address, host, port)
    app.run(host=host, port=port, debug=False, use_reloader=False)


def require_mutation(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if request.headers.get("X-Chain-Request") != "1":
            return jsonify({"error": "missing X-Chain-Request header"}), 400
        expected = current_app.config.get("API_TOKEN") or ""
        if expected:
            header = request.headers.get("Authorization", "")
            presented = header[7:] if header.startswith("Bearer ") else ""
            if not presented or not hmac.compare_digest(presented, expected):
                return jsonify({"error": "unauthorized"}), 401
        return fn(*args, **kwargs)

    return wrapper


def route_errors(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ChainError as err:
            return jsonify({"error": str(err)}), 400

    return wrapper


def _json_body() -> dict:
    content_type = request.content_type or ""
    if not content_type.startswith("application/json"):
        raise ChainError("content type must be application/json")
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ChainError("expected a JSON object")
    return data


def _difficulty_from_env() -> int:
    raw = os.environ.get("CHAIN_DIFFICULTY", str(DEFAULT_DIFFICULTY))
    try:
        return int(raw)
    except ValueError as err:
        raise ChainError("CHAIN_DIFFICULTY must be an integer") from err


if __name__ == "__main__":
    main()
