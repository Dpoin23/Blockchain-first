#!/usr/bin/env python3
"""Import the chain and mine one low-difficulty block. Does not open a port."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from chain.blockchain import Blockchain
    from chain.constants import BLOCK_REWARD
    from chain.wallet import Wallet

    chain = Blockchain(difficulty=1)
    if len(chain.chain) != 1:
        raise SystemExit(f"expected a genesis block, found {len(chain.chain)}")
    if sum(chain.balances().values()) != 0:
        raise SystemExit("genesis should start with an empty supply")

    miner = Wallet.generate()
    chain.mine(miner.address)
    balance = chain.balance_of(miner.address)
    if balance != BLOCK_REWARD or sum(chain.balances().values()) != BLOCK_REWARD:
        raise SystemExit(f"block reward mismatch: balance={balance}")

    print(f"smoke ok: reward={BLOCK_REWARD} length={len(chain.chain)}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as err:
        print(f"smoke failed: {err}", file=sys.stderr)
        sys.exit(1)
