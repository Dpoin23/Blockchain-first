"""Sign a transfer and submit it to a node you choose."""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
from pathlib import Path

from chain.errors import ChainError
from chain.peers import normalize_origin, request_json
from chain.wallet import Wallet


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Submit a signed transfer to a node")
    parser.add_argument("--node", default=os.environ.get("CHAIN_NODE", "http://127.0.0.1:5000"))
    parser.add_argument("--wallet", required=True, type=Path)
    parser.add_argument("--recipient", required=True)
    parser.add_argument("--amount", required=True, type=int)
    parser.add_argument("--fee", default=0, type=int)
    parser.add_argument(
        "--mine",
        action="store_true",
        help="ask the node to mine a block after the transfer is queued",
    )
    args = parser.parse_args(argv)
    try:
        origin = normalize_origin(args.node)
        token = os.environ.get("CHAIN_API_TOKEN", "")
        wallet = Wallet.load(args.wallet)
        status, account = _call("GET", f"{origin}/account/{wallet.address}", token=token)
        if status != 200:
            raise SystemExit(_error_text(account, "account lookup failed"))
        tx = wallet.sign_transaction(
            recipient=args.recipient,
            amount=args.amount,
            fee=args.fee,
            nonce=account["next_nonce"],
        )
        status, body = _call("POST", origin + "/transactions/new", payload=tx, token=token)
        if status != 201:
            raise SystemExit(_error_text(body, "transfer rejected"))
        print(json.dumps(body))
        if args.mine:
            status, mined = _call("POST", origin + "/mine", token=token)
            if status != 200:
                raise SystemExit(_error_text(mined, "mine failed"))
            print(json.dumps({"mined_index": mined["index"], "hash": mined["hash"]}))
    except ChainError as err:
        raise SystemExit(str(err)) from err


def _call(method: str, url: str, *, payload=None, token: str) -> tuple[int, dict]:
    try:
        return request_json(method, url, payload, token=token, timeout=30)
    except (urllib.error.URLError, OSError, ChainError) as err:
        raise SystemExit(f"node request failed: {err}") from err


def _error_text(body: dict, fallback: str) -> str:
    error = body.get("error") if isinstance(body, dict) else None
    return error if isinstance(error, str) else fallback


if __name__ == "__main__":
    main()
