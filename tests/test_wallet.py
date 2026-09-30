"""Wallet files stay private and signatures use the domain separator."""

import json
import stat

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from chain.encoding import canonical
from chain.errors import ChainError
from chain.transaction import signing_bytes
from chain.wallet import Wallet


def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / "wallet.json"
    wallet = Wallet.generate()
    wallet.save(path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    loaded = Wallet.load(path)
    assert loaded.address == wallet.address
    assert "private_key" in path.read_text(encoding="utf-8")


def test_repr_hides_the_secret():
    wallet = Wallet.generate()
    assert wallet.address in repr(wallet)
    secret = wallet._private_key.private_bytes_raw().hex()
    assert secret not in repr(wallet)


def test_load_rejects_address_mismatch(tmp_path):
    path = tmp_path / "wallet.json"
    Wallet.generate().save(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["address"] = "ab" * 32
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ChainError, match="does not match"):
        Wallet.load(path)


def test_signature_includes_domain_separator():
    wallet = Wallet.generate()
    recipient = Wallet.generate().address
    tx = wallet.sign_transaction(recipient=recipient, amount=3, fee=1, nonce=0)
    public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(wallet.address))
    public_key.verify(bytes.fromhex(tx["signature"]), signing_bytes(tx))
    bare = canonical(
        {
            "sender": tx["sender"],
            "recipient": tx["recipient"],
            "amount": tx["amount"],
            "fee": tx["fee"],
            "nonce": tx["nonce"],
        }
    )
    with pytest.raises(InvalidSignature):
        public_key.verify(bytes.fromhex(tx["signature"]), bare)


def test_sign_rejects_bad_amounts():
    wallet = Wallet.generate()
    recipient = Wallet.generate().address
    with pytest.raises(ChainError, match="amount"):
        wallet.sign_transaction(recipient=recipient, amount=0, fee=0, nonce=0)
    with pytest.raises(ChainError, match="amount"):
        wallet.sign_transaction(recipient=recipient, amount=True, fee=0, nonce=0)
    with pytest.raises(ChainError, match="fee"):
        wallet.sign_transaction(recipient=recipient, amount=1, fee=-1, nonce=0)
