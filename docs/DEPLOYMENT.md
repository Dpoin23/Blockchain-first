# Deployment plan

Two different deploys are easy to mix up. The Python node is the learning chain. The Solidity contract is a fixed-supply token for a public EVM network. Finish the earlier phase before you start the next one. This repository does not broadcast a mainnet transaction for you.

## Phase 0 — Local node

Goal: mine and transfer on one machine.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pytest
python -m chain.wallet new --out wallet.json
python blockchain.py
```

From another terminal, mine once, then pay the wallet you just created. The commands are in the [README](../README.md).

Exit when all of these are true:

- [ ] `pytest` passes
- [ ] `GET /node` returns an address and the response has no private key
- [ ] After one mine and one transfer, the recipient's `/account` balance is the amount you sent
- [ ] `data/` and `wallet.json` are untracked (`git status`)

## Phase 1 — Two local nodes

Goal: see longest-valid-chain sync, including a refusal.

Start a second process with its own port and data directory:

```bash
CHAIN_PORT=5001 CHAIN_DATA_DIR=data-node2 python blockchain.py
```

Register `http://127.0.0.1:5001` on the first node, mine two blocks on the second, then `POST /nodes/resolve` on the first. `replaced` should be true and the lengths should match.

Exit when all of these are true:

- [ ] Both processes use the same `CHAIN_DIFFICULTY`
- [ ] The shorter node adopts the longer valid chain
- [ ] You can point at the tests `test_longer_valid_chain_replaces_and_invalid_does_not` and `test_resolve_skips_invalid_peer_chains` and explain why a longer broken chain is ignored

## Phase 2 — A node that other machines can reach

Skip this phase if loopback is enough. Most learning setups should skip it.

Exit when all of these are true:

- [ ] `CHAIN_API_TOKEN` is a fresh value from `python -c "import secrets; print(secrets.token_urlsafe(32))"`, stored in a password manager, not in git
- [ ] The process is started with that token in the environment. It refuses a non-loopback host without one
- [ ] TLS is terminated by a reverse proxy you control. The app speaks HTTP behind that proxy
- [ ] The firewall allows the proxy port only, not a raw Flask port on `0.0.0.0`
- [ ] `data/` is on a disk that is not published and is included in your own backups

Mutations from another machine send both headers:

```bash
curl -s -X POST \
  -H 'X-Chain-Request: 1' \
  -H "Authorization: Bearer $CHAIN_API_TOKEN" \
  https://your-host.example/mine
```

## Phase 3 — Name, supply, and chain choice

Do this on paper before any public transaction. The worksheet and the failure examples are in [MEME_COIN.md](MEME_COIN.md).

Write down:

- Network for the first public deploy (a testnet: Ethereum Sepolia or Base Sepolia)
- Token name and ticker
- Decimals (18 unless you have a written reason)
- Human supply, the number you would say out loud
- Raw supply: human supply × 10^decimals
- Recipient address that will receive the single mint
- The URL or social account where you will publish the contract address

Worked raw supply for 1,000,000 tokens at 18 decimals:

```text
1000000000000000000000000
```

That is `1000000 * 10**18`. Minting `1000000` by mistake creates 1,000,000 wei, which is a millionth of a millionth of one token. Minting an extra 18 zeros creates a supply you cannot explain.

Exit when all of these are true:

- [ ] The naming worksheet has one row you are willing to keep, and the searches in that doc have been run
- [ ] Name, ticker, human supply, raw supply, decimals, and recipient are written down and match
- [ ] The recipient is an address you control on the testnet, separate from any wallet you use for daily mainnet funds

## Phase 4 — Public testnet

Goal: deploy `contracts/FixedSupplyToken.sol`, verify the source, and transfer tokens between two testnet addresses you control.

Install Foundry and the pinned library from the repository root:

```bash
forge install OpenZeppelin/openzeppelin-contracts@v5.7.0 --no-commit
forge build
```

Import a **testnet-only** deployer into a Foundry keystore. The prompt reads the key without putting it in the command line:

```bash
cast wallet import testnet-deployer --interactive
```

Dry-run first (no `--broadcast`). `--constructor-args` goes last. Replace the name, ticker, raw supply, and recipient with the sheet from phase 3.

```bash
forge create contracts/FixedSupplyToken.sol:FixedSupplyToken \
  --rpc-url "$TESTNET_RPC_URL" \
  --account testnet-deployer \
  --constructor-args "Example Name" "EXM" 1000000000000000000000000 0xYourTestnetRecipient
```

When the constructor arguments in the output match the sheet, broadcast:

```bash
forge create contracts/FixedSupplyToken.sol:FixedSupplyToken \
  --rpc-url "$TESTNET_RPC_URL" \
  --account testnet-deployer \
  --broadcast \
  --constructor-args "Example Name" "EXM" 1000000000000000000000000 0xYourTestnetRecipient
```

Verify against the explorer. Constructor arguments for verification are ABI-encoded:

```bash
cast abi-encode "constructor(string,string,uint256,address)" \
  "Example Name" "EXM" 1000000000000000000000000 0xYourTestnetRecipient
```

Pass that blob to `forge verify-contract` for the chain you used (`--chain sepolia` or the Base Sepolia chain id `84532`). Set `ETHERSCAN_API_KEY` or the Basescan equivalent in the environment for that one command.

Then, from the recipient, send a small amount to a second testnet address you control and confirm both balances on the explorer.

Exit when all of these are true:

- [ ] `forge build` succeeded against OpenZeppelin Contracts v5.7.0
- [ ] The deployed bytecode matches the source you verified
- [ ] Token name, symbol, and total supply on the explorer match the sheet
- [ ] A transfer between two of your testnet wallets succeeded
- [ ] The contract address is published on the site or account you named in phase 3
- [ ] The deployer key has no mainnet funds

`TESTNET_RPC_URL` is an endpoint you choose (the chain's public RPC or one from your own provider account). Keep that URL's credentials out of git the same way you keep `CHAIN_API_TOKEN` out of git.

## Phase 5 — Mainnet gate

Mainnet is a separate decision after the testnet exit criteria have been true for a build you can still reproduce. This repository stops here on purpose.

All of these have to be true before you broadcast a mainnet create:

- [ ] The testnet contract you verified is the same source, compiler `0.8.24`, and OpenZeppelin pin you intend to deploy
- [ ] A person other than the author has read `contracts/FixedSupplyToken.sol` and the constructor arguments
- [ ] The deployer is a hardware wallet or a dedicated keystore created for this deploy, funded only with the gas you are willing to spend
- [ ] You can say the human supply, the raw supply, and the recipient address without looking at a chat transcript
- [ ] You are not collecting other people's money in order to deploy
- [ ] If you add liquidity, the lock transaction (locker, amount, and unlock time) will be published next to the contract address. If you will not add liquidity, that sentence is published too

When those are true, repeat the phase 4 command with a mainnet RPC and the mainnet account. Verify immediately, before you announce the address.

## Rollback

- Local chain: stop the process and move `data/` aside. The next start creates a new genesis. Old keys remain valid addresses with a zero balance on the new chain.
- Testnet token: you cannot delete a contract. You can stop telling people to use an address. Publish the correction on the same account that announced it.
- Mainnet token: the same rule. A fixed-supply contract has no admin function that recalls balances. That is the point of the shape in [MEME_COIN.md](MEME_COIN.md).
