"""Content hashing. Spec section 11.3.

The sha256 of every source is recorded before and after ingestion, to detect
read-path corruption. Hashing is streamed: SDIP must not allocate proportionally to
an attacker-controlled file size (spec 11.4).
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from pathlib import Path

_CHUNK = 1 << 20  # 1 MiB. Bounded regardless of input size.


def sha256_file(path: str | Path, *, chunk_size: int = _CHUNK) -> str:
    """Return the lowercase hex sha256 of a file, streamed.

    Args:
        path: File to hash.
        chunk_size: Read size in bytes. Bounded by design.

    Returns:
        64-character lowercase hex digest.
    """
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while block := handle.read(chunk_size):
            digest.update(block)
    return digest.hexdigest()


def sha256_tree(root: str | Path, *, exclude: Iterable[str] = ()) -> dict[str, str]:
    """Return ``{relative_posix_path: sha256}`` for every file under ``root``.

    Deterministic: entries are produced in sorted path order so two runs over the
    same tree produce byte-identical output (G6).

    Args:
        root: Directory to walk.
        exclude: Path *parts* to skip entirely, e.g. ``(".git",)``.

    Returns:
        Mapping of relative POSIX path to hex digest, in sorted key order.
    """
    root_path = Path(root)
    skip = set(exclude)
    out: dict[str, str] = {}
    for path in sorted(root_path.rglob("*")):
        if not path.is_file() or skip.intersection(path.relative_to(root_path).parts):
            continue
        out[path.relative_to(root_path).as_posix()] = sha256_file(path)
    return out
