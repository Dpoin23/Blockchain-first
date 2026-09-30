"""Consensus parameters. Changing these is a hard fork."""

BLOCK_REWARD = 50
COINBASE_SENDER = "coinbase"
GENESIS_PREVIOUS_HASH = "0" * 64

# Domain separator so a signature from this chain cannot be replayed elsewhere.
TX_DOMAIN = b"blockchain-first/tx/v1\n"

MIN_DIFFICULTY = 1
MAX_DIFFICULTY = 5
DEFAULT_DIFFICULTY = 4

MAX_AMOUNT = 10**18
MAX_PROOF = 20_000_000
MAX_TX_PER_BLOCK = 100
MAX_MEMPOOL = 1_000
MAX_CHAIN_LENGTH = 10_000
MAX_FUTURE_DRIFT_SECONDS = 15 * 60
MAX_PEERS = 32

ADDRESS_LENGTH = 64
SIGNATURE_LENGTH = 128
FILE_VERSION = 1
