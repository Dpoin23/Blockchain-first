"""Canonical encoding. Hashes and signatures use these bytes and no others."""

import hashlib
import json
from typing import Any


def canonical(data: Any) -> bytes:
    """Stable UTF-8 JSON: sorted keys, no insignificant whitespace, no NaN."""
    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
