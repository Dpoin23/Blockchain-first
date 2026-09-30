# Security model

This node is a learning chain with real cryptographic checks and a small, explicit trust boundary. It is safe to run on your own machine. It is not a settlement network for money.

## Assets

- Private keys in `data/node_key.json` and any wallet file you create. Mode `0600`. The chain file stores public data only.
- Account balances and nonces derived by replaying the chain. Clients do not get to declare a balance.
- CPU time spent mining, and the peer list the node will contact.

## What a single honest node guarantees

- A transfer is included only when the signature verifies under the sender's address, the nonce matches, and the sender's confirmed balance covers amount plus fee.
- The signature covers `blockchain-first/tx/v1`, the sender, recipient, amount, fee, and nonce. A signature from another protocol, or a edited amount, does not verify.
- Block hashes are SHA-256 over a canonical header. The header includes a hash of the transaction list, so changing a transaction changes the header and breaks the proof of work.
- Coinbase is the first transaction of every non-genesis block. Its amount has to equal 50 plus the fees in that block. There is no other mint.
- A peer chain replaces the local one only when it is strictly longer and passes the same validation. Equal length keeps the local chain.
- Registered peer URLs are `http` or `https` with a host and port and no path, userinfo, query, or fragment. Multicast, link-local (including `169.254.169.254`), and unspecified addresses are rejected before a socket is opened. Redirects are not followed. Responses are size-capped.

## What it does not guarantee

- **Economic finality.** Difficulty is an integer from 1 to 5 (default 4). That is a few leading zero nibbles, chosen so a laptop can mine. Anyone who can feed this node a longer valid chain can replace history. Keep real value off it.
- **Peer authentication.** A registered peer is trusted to offer chains, which are then fully validated. The transport is plain HTTP unless you terminate TLS yourself. DNS rebinding after the allow check is a residual risk; register peers by IP when you can, and only peers you run.
- **Availability under load.** `/mine` holds the chain lock while it searches for a proof. Leave the server on loopback. The custom header stops a normal browser form from mining as a side effect of visiting a page. It is not an authentication system.
- **Smart contracts, light clients, or cross-chain transfers.** There is no bridge. Coins here do not become tokens on Ethereum, Base, or Solana.

## Operator rules

1. Run from the repository root so `data/` stays next to the code you expect.
2. Leave `CHAIN_HOST` at `127.0.0.1`. The process exits if the host is anything else and `CHAIN_API_TOKEN` is empty.
3. If the node must leave the machine, set a long random token, bind a specific interface on purpose, and put TLS on a reverse proxy you control. Mutations then require both `X-Chain-Request: 1` and `Authorization: Bearer <token>`. Reads stay unauthenticated because chain data is public.
4. Treat wallet files like passwords. `python -m chain.wallet new` will not overwrite an existing file unless you pass `--force`. The file is chmod'd to `0600` on write, and loosened permissions are tightened on load.
5. Use one data directory per node. Two processes on the same `CHAIN_DATA_DIR` will fight over the chain file and the key.
6. Upgrade by reading the chain file's `"version"` field. Version 1 is the only format this code loads. A difficulty change does not migrate an existing file; start a new data directory. Changing `BLOCK_REWARD` or the signature domain is a hard fork.
7. Install dependencies from `requirements.txt` inside a virtualenv. Those pins are the versions the tests ran against.

## API abuse cases the tests lock in

- Missing `X-Chain-Request` does not mine.
- A wrong bearer token does not mine. Chain reads still succeed.
- A metadata-address peer is rejected and the peer list stays empty.
- A tampered amount, a flipped signature byte, an overspend, and a reused nonce never enter the mempool.
- Supply after any sequence of valid blocks equals `50 * (length - 1)`.

## Dependency and process notes

Signature and key generation go through the `cryptography` library's Ed25519 implementation. The project does not ship its own elliptic-curve arithmetic. Flask is the HTTP adapter. Debug and the reloader are off so the process does not expose an interactive debugger or mine twice on startup.
