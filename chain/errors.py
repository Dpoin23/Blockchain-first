"""Errors that are safe to return to an API client."""


class ChainError(ValueError):
    """A block, transaction, or peer failed validation."""
