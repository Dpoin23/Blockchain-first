# FixedSupplyToken

EVM reference for a meme coin whose entire supply is created in the constructor. The contract has no owner, no second mint, no pause, and no fee.

It depends on OpenZeppelin Contracts 5.x. Install that from the repository root when you are ready to compile:

```bash
forge install OpenZeppelin/openzeppelin-contracts@v5.7.0 --no-commit
forge build
```

`lib/` is gitignored. The import path is `@openzeppelin/contracts/...`, wired in `remappings.txt`.

Deploy steps, the raw-unit supply footgun, and the testnet-before-mainnet gate are in [docs/DEPLOYMENT.md](../docs/DEPLOYMENT.md). Naming and token choices are in [docs/MEME_COIN.md](../docs/MEME_COIN.md).

This file is a reference. Nothing in this repository broadcasts a mainnet transaction.
