"""Ed25519 wallets. Private keys stay in mode-0600 files and never in the chain."""

from __future__ import annotations

import argparse
import json
import os
import stat
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from chain.constants import ADDRESS_LENGTH, FILE_VERSION
from chain.errors import ChainError
from chain.storage import atomic_write_text
from chain.transaction import signing_bytes, user_tx_fields

_SECRET_MODE = 0o600


class Wallet:
    def __init__(self, private_key: Ed25519PrivateKey):
        self._private_key = private_key
        public = private_key.public_key().public_bytes_raw()
        self.address = public.hex()

    def __repr__(self) -> str:
        return f"Wallet(address={self.address})"

    @classmethod
    def generate(cls) -> Wallet:
        return cls(Ed25519PrivateKey.generate())

    @classmethod
    def from_seed_hex(cls, seed_hex: str) -> Wallet:
        if not isinstance(seed_hex, str) or len(seed_hex) != ADDRESS_LENGTH:
            raise ChainError("private key must be 32 bytes of hex")
        try:
            seed = bytes.fromhex(seed_hex)
        except ValueError as err:
            raise ChainError("private key must be 32 bytes of hex") from err
        if len(seed) != 32:
            raise ChainError("private key must be 32 bytes of hex")
        return cls(Ed25519PrivateKey.from_private_bytes(seed))

    def save(self, path: Path) -> None:
        payload = {
            "version": FILE_VERSION,
            "address": self.address,
            "private_key": self._private_key.private_bytes_raw().hex(),
        }
        atomic_write_text(path, json.dumps(payload, indent=2) + "\n", mode=_SECRET_MODE)

    @classmethod
    def load(cls, path: Path) -> Wallet:
        _tighten_permissions(path)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as err:
            raise ChainError("wallet file is unreadable") from err
        if not isinstance(raw, dict) or set(raw) != {"version", "address", "private_key"}:
            raise ChainError("wallet file has an unexpected shape")
        if raw.get("version") != FILE_VERSION:
            raise ChainError("unsupported wallet file version")
        wallet = cls.from_seed_hex(raw["private_key"])
        if wallet.address != raw["address"]:
            raise ChainError("wallet address does not match the private key")
        return wallet

    @classmethod
    def load_or_create(cls, path: Path) -> Wallet:
        if path.exists():
            return cls.load(path)
        wallet = cls.generate()
        wallet.save(path)
        return wallet

    def sign_transaction(self, *, recipient: str, amount: int, fee: int, nonce: int) -> dict:
        unsigned = {
            "sender": self.address,
            "recipient": recipient,
            "amount": amount,
            "fee": fee,
            "nonce": nonce,
            "signature": "",
        }
        # Reject a bad field before it is signed, so the key never signs junk.
        normalized = user_tx_fields(unsigned, signed=False)
        signature = self._private_key.sign(signing_bytes(normalized))
        normalized["signature"] = signature.hex()
        return normalized


def _tighten_permissions(path: Path) -> None:
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        os.chmod(path, _SECRET_MODE)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Create or inspect a local wallet file")
    sub = parser.add_subparsers(dest="command", required=True)

    new_cmd = sub.add_parser("new", help="write a new key file (mode 0600)")
    new_cmd.add_argument("--out", required=True, type=Path, help="path to create")
    new_cmd.add_argument("--force", action="store_true", help="replace an existing file")

    show = sub.add_parser("address", help="print the public address only")
    show.add_argument("--wallet", required=True, type=Path)

    args = parser.parse_args(argv)
    if args.command == "new":
        if args.out.exists() and not args.force:
            raise SystemExit(f"refusing to overwrite {args.out}")
        wallet = Wallet.generate()
        wallet.save(args.out)
        print(wallet.address)
        return
    wallet = Wallet.load(args.wallet)
    print(wallet.address)


if __name__ == "__main__":
    main()
