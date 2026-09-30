"""Signed account transfers and the coinbase reward."""

from __future__ import annotations

import re

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from chain.constants import (
    ADDRESS_LENGTH,
    BLOCK_REWARD,
    COINBASE_SENDER,
    MAX_AMOUNT,
    MAX_TX_PER_BLOCK,
    SIGNATURE_LENGTH,
    TX_DOMAIN,
)
from chain.encoding import canonical
from chain.errors import ChainError

_ADDRESS = re.compile(rf"^[0-9a-f]{{{ADDRESS_LENGTH}}}$")
_SIGNATURE = re.compile(rf"^[0-9a-f]{{{SIGNATURE_LENGTH}}}$")
_TX_KEYS = {"sender", "recipient", "amount", "fee", "nonce", "signature"}


def signing_bytes(tx: dict) -> bytes:
    body = {
        "sender": tx["sender"],
        "recipient": tx["recipient"],
        "amount": tx["amount"],
        "fee": tx["fee"],
        "nonce": tx["nonce"],
    }
    return TX_DOMAIN + canonical(body)


def user_tx_fields(raw: dict, *, signed: bool) -> dict:
    if not isinstance(raw, dict) or set(raw) != _TX_KEYS:
        raise ChainError("transaction fields are invalid")
    sender = raw["sender"]
    recipient = raw["recipient"]
    if not isinstance(sender, str) or not _ADDRESS.fullmatch(sender):
        raise ChainError("sender is not a valid address")
    if not isinstance(recipient, str) or not _ADDRESS.fullmatch(recipient):
        raise ChainError("recipient is not a valid address")
    amount = _require_int("amount", raw["amount"], minimum=1, maximum=MAX_AMOUNT)
    fee = _require_int("fee", raw["fee"], minimum=0, maximum=MAX_AMOUNT)
    nonce = _require_int("nonce", raw["nonce"], minimum=0, maximum=MAX_AMOUNT)
    signature = raw["signature"]
    if signed:
        if not isinstance(signature, str) or not _SIGNATURE.fullmatch(signature):
            raise ChainError("signature is invalid")
    elif signature != "":
        raise ChainError("signature is invalid")
    return {
        "sender": sender,
        "recipient": recipient,
        "amount": amount,
        "fee": fee,
        "nonce": nonce,
        "signature": signature,
    }


def normalize_user_tx(raw: dict) -> dict:
    tx = user_tx_fields(raw, signed=True)
    _verify(tx)
    return tx


def normalize_coinbase(raw: dict, *, expected_amount: int) -> dict:
    if not isinstance(raw, dict) or set(raw) != _TX_KEYS:
        raise ChainError("coinbase fields are invalid")
    if raw["sender"] != COINBASE_SENDER or raw["signature"] != "":
        raise ChainError("coinbase is invalid")
    if raw["fee"] != 0 or raw["nonce"] != 0:
        raise ChainError("coinbase is invalid")
    recipient = raw["recipient"]
    if not isinstance(recipient, str) or not _ADDRESS.fullmatch(recipient):
        raise ChainError("coinbase recipient is invalid")
    amount = _require_int("amount", raw["amount"], minimum=1, maximum=MAX_AMOUNT)
    if amount != expected_amount:
        raise ChainError("coinbase amount does not match the block reward and fees")
    return {
        "sender": COINBASE_SENDER,
        "recipient": recipient,
        "amount": amount,
        "fee": 0,
        "nonce": 0,
        "signature": "",
    }


def coinbase_tx(recipient: str, amount: int) -> dict:
    return normalize_coinbase(
        {
            "sender": COINBASE_SENDER,
            "recipient": recipient,
            "amount": amount,
            "fee": 0,
            "nonce": 0,
            "signature": "",
        },
        expected_amount=amount,
    )


def apply_user_tx(tx: dict, balances: dict[str, int], nonces: dict[str, int]) -> int:
    """Move amount and fee. Returns the fee so the coinbase can pay the miner."""
    sender = tx["sender"]
    expected_nonce = nonces.get(sender, 0)
    if tx["nonce"] != expected_nonce:
        raise ChainError("nonce does not match the account")
    cost = tx["amount"] + tx["fee"]
    balance = balances.get(sender, 0)
    if balance < cost:
        raise ChainError("insufficient funds")
    balances[sender] = balance - cost
    recipient = tx["recipient"]
    balances[recipient] = balances.get(recipient, 0) + tx["amount"]
    nonces[sender] = expected_nonce + 1
    return tx["fee"]


def apply_coinbase(tx: dict, balances: dict[str, int]) -> None:
    recipient = tx["recipient"]
    balances[recipient] = balances.get(recipient, 0) + tx["amount"]


def apply_block_transactions(transactions: list, balances: dict[str, int], nonces: dict[str, int]) -> None:
    if not isinstance(transactions, list) or not transactions:
        raise ChainError("block requires a coinbase transaction")
    if len(transactions) > MAX_TX_PER_BLOCK:
        raise ChainError("block has too many transactions")

    scratch_balances = dict(balances)
    scratch_nonces = dict(nonces)
    fees = 0
    for raw in transactions[1:]:
        tx = normalize_user_tx(raw)
        fees += apply_user_tx(tx, scratch_balances, scratch_nonces)
    reward = BLOCK_REWARD + fees
    if reward > MAX_AMOUNT:
        raise ChainError("coinbase amount is out of range")
    coinbase = normalize_coinbase(transactions[0], expected_amount=reward)
    apply_coinbase(coinbase, scratch_balances)
    balances.clear()
    balances.update(scratch_balances)
    nonces.clear()
    nonces.update(scratch_nonces)


def _verify(tx: dict) -> None:
    try:
        public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(tx["sender"]))
        public_key.verify(bytes.fromhex(tx["signature"]), signing_bytes(tx))
    except (InvalidSignature, ValueError) as err:
        raise ChainError("invalid signature") from err


def _require_int(name: str, value: object, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ChainError(f"{name} must be an integer")
    if value < minimum or value > maximum:
        raise ChainError(f"{name} is out of range")
    return value
