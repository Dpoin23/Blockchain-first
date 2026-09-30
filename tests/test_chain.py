"""Consensus invariants: signatures, supply, and longest valid chain."""

import copy

import pytest

from chain.block import block_hash
from chain.blockchain import Blockchain, validate_chain
from chain.constants import BLOCK_REWARD
from chain.errors import ChainError
from chain.wallet import Wallet


def _paid(chain: Blockchain, miner: Wallet, recipient: str, amount: int, fee: int = 0) -> None:
    chain.add_transaction(
        miner.sign_transaction(
            recipient=recipient,
            amount=amount,
            fee=fee,
            nonce=chain.next_nonce(miner.address),
        )
    )


def test_genesis_is_deterministic():
    first = Blockchain(difficulty=2)
    second = Blockchain(difficulty=2)
    assert first.chain == second.chain
    assert sum(first.balances().values()) == 0


def test_mine_pays_only_the_miner_and_conserves_supply():
    chain = Blockchain(difficulty=1)
    miner = Wallet.generate()
    chain.mine(miner.address)
    chain.mine(miner.address)
    assert chain.balance_of(miner.address) == 2 * BLOCK_REWARD
    assert sum(chain.balances().values()) == 2 * BLOCK_REWARD


def test_transfer_moves_value_and_rejects_replay():
    chain = Blockchain(difficulty=1)
    miner = Wallet.generate()
    recipient = Wallet.generate()
    chain.mine(miner.address)
    _paid(chain, miner, recipient.address, amount=10, fee=1)
    chain.mine(miner.address)

    assert chain.balance_of(recipient.address) == 10
    assert chain.balance_of(miner.address) == 2 * BLOCK_REWARD - 10
    assert sum(chain.balances().values()) == 2 * BLOCK_REWARD
    assert chain.confirmed_nonce(miner.address) == 1

    replay = miner.sign_transaction(recipient=recipient.address, amount=1, fee=0, nonce=0)
    with pytest.raises(ChainError, match="nonce"):
        chain.add_transaction(replay)


def test_overspend_and_gap_nonce_never_enter_the_mempool():
    chain = Blockchain(difficulty=1)
    miner = Wallet.generate()
    chain.mine(miner.address)
    with pytest.raises(ChainError, match="insufficient"):
        _paid(chain, miner, Wallet.generate().address, amount=BLOCK_REWARD + 1)
    with pytest.raises(ChainError, match="nonce"):
        chain.add_transaction(
            miner.sign_transaction(
                recipient=Wallet.generate().address,
                amount=1,
                fee=0,
                nonce=1,
            )
        )
    assert chain.mempool_copy() == []
    assert chain.balance_of(miner.address) == BLOCK_REWARD


def test_tampered_transaction_does_not_verify():
    chain = Blockchain(difficulty=1)
    miner = Wallet.generate()
    chain.mine(miner.address)
    tx = miner.sign_transaction(
        recipient=Wallet.generate().address,
        amount=4,
        fee=0,
        nonce=0,
    )
    tx["amount"] = 5
    with pytest.raises(ChainError, match="signature"):
        chain.add_transaction(tx)


def test_forged_signature_is_rejected():
    chain = Blockchain(difficulty=1)
    miner = Wallet.generate()
    chain.mine(miner.address)
    tx = miner.sign_transaction(
        recipient=Wallet.generate().address,
        amount=4,
        fee=0,
        nonce=0,
    )
    flipped = "0" if tx["signature"][0] != "0" else "1"
    tx["signature"] = flipped + tx["signature"][1:]
    with pytest.raises(ChainError, match="signature"):
        chain.add_transaction(tx)


def test_header_commits_to_transactions_and_proof():
    chain = Blockchain(difficulty=1)
    miner = Wallet.generate()
    chain.mine(miner.address)
    forged = copy.deepcopy(chain.chain_copy())
    forged[-1]["transactions"][0]["recipient"] = Wallet.generate().address
    assert block_hash(forged[-1]) != block_hash(chain.chain_copy()[-1])
    # A changed transaction usually misses the target, but difficulty 1 still
    # accepts 1 in 16 hashes. Pick a proof that misses so the rejection is certain.
    for proof in range(64):
        forged[-1]["proof"] = proof
        if not block_hash(forged[-1]).startswith("0"):
            break
    else:
        raise AssertionError("expected a proof that misses difficulty 1")
    with pytest.raises(ChainError, match="proof of work"):
        validate_chain(forged, chain.difficulty)


def test_future_and_backwards_timestamps_are_rejected():
    chain = Blockchain(difficulty=1)
    miner = Wallet.generate()
    chain.mine(miner.address)
    chain.mine(miner.address)
    backwards = copy.deepcopy(chain.chain_copy())
    backwards[-1]["timestamp"] = 0
    with pytest.raises(ChainError, match="backwards"):
        validate_chain(backwards, chain.difficulty)

    future = copy.deepcopy(chain.chain_copy())
    future[-1]["timestamp"] = 10**12
    with pytest.raises(ChainError, match="future"):
        validate_chain(future, chain.difficulty)


def test_longer_valid_chain_replaces_and_invalid_does_not():
    local = Blockchain(difficulty=1)
    remote = Blockchain(difficulty=1)
    miner = Wallet.generate()
    remote.mine(miner.address)
    remote.mine(miner.address)
    stolen = copy.deepcopy(remote.chain_copy())
    stolen[-1]["transactions"][0]["amount"] = BLOCK_REWARD + 1
    assert local.adopt_chain_if_longer(stolen) is False
    assert len(local.chain_copy()) == 1

    assert local.adopt_chain_if_longer(remote.chain_copy()) is True
    assert local.balance_of(miner.address) == 2 * BLOCK_REWARD

    rival = Blockchain(difficulty=1)
    other = Wallet.generate()
    rival.mine(other.address)
    rival.mine(other.address)
    assert local.adopt_chain_if_longer(rival.chain_copy()) is False
    assert local.balance_of(other.address) == 0


def test_resolve_skips_invalid_peer_chains():
    local = Blockchain(difficulty=1)
    good = Blockchain(difficulty=1)
    miner = Wallet.generate()
    good.mine(miner.address)
    broken = copy.deepcopy(good.chain_copy())
    broken[-1]["proof"] = 0
    local.add_peer("http://127.0.0.1:9")

    assert local.resolve(lambda _origin: broken) is False
    assert len(local.chain_copy()) == 1
    assert local.resolve(lambda _origin: good.chain_copy()) is True
    assert local.balance_of(miner.address) == BLOCK_REWARD


def test_difficulty_mismatch_is_not_adopted():
    local = Blockchain(difficulty=1)
    other = Blockchain(difficulty=2)
    other.mine(Wallet.generate().address)
    assert local.adopt_chain_if_longer(other.chain_copy()) is False


def test_disk_round_trip_keeps_chain_and_mempool(tmp_path):
    path = tmp_path / "chain.json"
    chain = Blockchain(difficulty=1, store_path=path)
    miner = Wallet.generate()
    chain.mine(miner.address)
    recipient = Wallet.generate().address
    tx = miner.sign_transaction(recipient=recipient, amount=2, fee=0, nonce=0)
    chain.add_transaction(tx)

    loaded = Blockchain.from_disk(path, difficulty=1)
    assert loaded.chain_copy() == chain.chain_copy()
    assert loaded.mempool_copy() == [tx]
    assert loaded.balance_of(miner.address) == BLOCK_REWARD
    stored = path.read_text(encoding="utf-8")
    assert miner._private_key.private_bytes_raw().hex() not in stored


def test_many_transfers_conserve_supply():
    chain = Blockchain(difficulty=1)
    wallets = [Wallet.generate() for _ in range(3)]
    chain.mine(wallets[0].address)
    for step in range(8):
        sender = wallets[step % 3]
        balance = chain.balance_of(sender.address)
        if balance < 2:
            chain.mine(sender.address)
        else:
            _paid(chain, sender, wallets[(step + 1) % 3].address, amount=1, fee=0)
            chain.mine(wallets[step % 3].address)
        assert sum(chain.balances().values()) == (len(chain.chain_copy()) - 1) * BLOCK_REWARD
