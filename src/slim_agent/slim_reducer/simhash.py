"""SimHash: character n-gram → 64-bit fingerprint → hamming distance similarity.

Useful for catching near-duplicate text across languages and noise (punctuation,
case, word reorder). Used by SlimReducer as a second similarity signal alongside
tag Jaccard.
"""

from __future__ import annotations

import hashlib
import re

_FINGERPRINT_BITS = 64
_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def _ngrams(text: str, n: int = 3) -> list[str]:
    """Character n-grams with whitespace normalised."""
    # Normalise: lowercase + collapse whitespace + strip punctuation boundaries
    norm = " ".join(_TOKEN_RE.findall(text.lower()))
    if len(norm) < n:
        return [norm] if norm else []
    return [norm[i : i + n] for i in range(len(norm) - n + 1)]


def _hash64(token: str) -> int:
    """Stable 64-bit hash of a token (uses BLAKE2b, then masks to 64 bits)."""
    h = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(h, "big")


def simhash(text: str, n: int = 4) -> int:
    """Compute 64-bit SimHash fingerprint of text via character n-grams.

    Returns an integer in [0, 2**64). Two texts with many shared n-grams will
    have similar fingerprints (small Hamming distance).

    Default n=4 balances CJK (where 4-grams still have signal even on short
    summaries) vs English (where 4-grams cut false positives from short overlap).
    """
    weights = [0] * _FINGERPRINT_BITS
    for gram in _ngrams(text, n=n):
        h = _hash64(gram)
        for bit in range(_FINGERPRINT_BITS):
            if h & (1 << bit):
                weights[bit] += 1
            else:
                weights[bit] -= 1

    fp = 0
    for bit in range(_FINGERPRINT_BITS):
        if weights[bit] > 0:
            fp |= 1 << bit
    return fp


def hamming(a: int, b: int) -> int:
    """Number of differing bits between two 64-bit fingerprints."""
    return bin(a ^ b).count("1")


def simhash_similarity(a: int, b: int) -> float:
    """Normalised similarity: 1.0 = identical, 0.0 = completely different."""
    return 1.0 - hamming(a, b) / _FINGERPRINT_BITS
