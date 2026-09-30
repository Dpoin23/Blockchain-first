#!/usr/bin/env python3
"""Verify a node app can be constructed and answer /health without binding a port."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from chain.blockchain import Blockchain
    from chain.node import bind_is_allowed, create_app

    if bind_is_allowed("0.0.0.0", ""):
        raise SystemExit("a public bind must require CHAIN_API_TOKEN")
    if not bind_is_allowed("127.0.0.1", ""):
        raise SystemExit("loopback should be allowed without a token")

    with tempfile.TemporaryDirectory() as tmp:
        app = create_app(blockchain=Blockchain(difficulty=1), data_dir=tmp)
        response = app.test_client().get("/health")
        body = response.get_json(silent=True) or {}
        if response.status_code != 200 or body.get("status") != "ok" or body.get("length") != 1:
            raise SystemExit(f"health check failed: {response.status_code} {body}")
        info = app.test_client().get("/node").get_json(silent=True) or {}
        if set(info) != {"address"} or not info["address"]:
            raise SystemExit(f"node info should be the public address only: {info}")

    print("runnable ok: create_app + /health")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as err:
        print(f"runnable check failed: {err}", file=sys.stderr)
        sys.exit(1)
