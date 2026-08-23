"""A synthetic SEG-Y whose 3200-byte textual header **cannot be decoded**. Debt D17.

§4.2 requires the raw 3200 bytes preserved and the decode failure recorded whenever the
textual header cannot be decoded — *"decode failure is not an ingestion failure; silent
substitution is."* That clause was unmeasurable until this fixture existed: every other
fixture in the repository carries a well-formed EBCDIC header, so no test could reach
the branch, and D17 stayed open on a claim about a code path nobody had run.

**What "cannot be decoded" means here, precisely.** A SEG-Y textual header is 40 cards
of 80 characters in EBCDIC. The pinned ``segy`` 0.6.0 decodes it by mapping each byte
through ``EBCDIC_TO_ASCII`` and then calling ``bytes.decode("ascii", errors="replace")``
— so the *decode* never raises; it silently yields ``U+FFFD`` for every byte whose EBCDIC
translation lands above 127. Measured against that table: **128 of the 256 possible byte
values translate above 127** and a further **33 translate to non-printable ASCII**, so
161 of 256 byte values cannot appear in a conforming card. The bytes planted below are
drawn from that set. They are not merely *unusual text* — they are values for which no
printable character exists on either side of the EBCDIC/ASCII boundary.

Built by corrupting a known-good fixture rather than by writing a new file end to end:
the only property under test is the textual header, and every other byte in the file
must stay identical to the conforming article so that a difference in outcome can be
attributed to the header and to nothing else. That makes the pair a controlled
comparison rather than two unrelated files.

Deterministic: fixed positions, fixed values, no clock and no RNG.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sdip._pins import SEGY_TEXTUAL_HEADER_BYTES as TEXTUAL_HEADER_BYTES
from tests.fixtures.generators.poststack3d import SyntheticSegy, make_poststack3d

PLANTED: tuple[tuple[int, int], ...] = (
    (0, 0x04),
    (1, 0x00),
    (2, 0xFF),
    (79, 0x04),
    (80, 0x00),
    (160, 0xFF),
    (1600, 0x1A),
    (3199, 0x00),
)
"""``(offset, byte)`` pairs written over the encoded textual header. 0-based offsets.

Chosen to spread the damage across the structure rather than to cluster it: the first
card's start and end (0, 1, 2, 79), the start of the second and third cards (80, 160),
the middle of the header (1600) and its very last byte (3199). A checker that looked at
only the first card, or stopped at the first offence, would pass on some of these and
fail on others, and would be caught by the count.

Every value is one of the 161 that cannot survive the EBCDIC-to-printable-ASCII round
trip. Measured against ``segy.ebcdic.EBCDIC_TO_ASCII``: ``0x04`` translates to 156,
``0xFF`` to 255, ``0x1A`` to 146 — all above 127, so all become ``U+FFFD`` — and
``0x00`` to 0, the NUL control, which is inside ASCII but not printable. The set covers
both ways a card can fail.
"""

EXPECTED_OFFENDING_CELLS: tuple[tuple[int, int], ...] = (
    (0, 0),
    (0, 1),
    (0, 2),
    (0, 79),
    (1, 0),
    (2, 0),
    (20, 0),
    (39, 79),
)
"""``(row, column)`` a correct classifier must report, derived from :data:`PLANTED`.

Committed as a literal rather than computed from ``PLANTED`` inside the test: a test
that derives its expectation from the same arithmetic as the code under test asserts
that the arithmetic is self-consistent, not that it is right. These eight cells were
read out of upstream's own ``ValueError`` message on this exact fixture — see
``DECISIONS.md`` D-0055.
"""


@dataclass(frozen=True, slots=True)
class UndecodableSegy:
    """The non-conforming file, and the conforming one it was derived from."""

    article: SyntheticSegy
    """The generated article. ``article.path`` is the corrupted file on disk."""

    conforming_textual: bytes
    """The 3200 textual-header bytes **before** planting. The controlled comparison."""

    @property
    def path(self) -> Path:
        """The non-conforming SEG-Y."""
        return self.article.path

    @property
    def textual_header(self) -> bytes:
        """The 3200 non-conforming textual-header bytes, as written to disk."""
        return self.article.path.read_bytes()[:TEXTUAL_HEADER_BYTES]


def make_undecodable_textual_header(
    path: str | Path,
    *,
    n_inline: int = 3,
    n_crossline: int = 4,
    n_samples: int = 16,
) -> UndecodableSegy:
    """Write a deterministic SEG-Y whose textual header cannot be decoded.

    Small by default — 12 traces — because the property under test lives entirely in the
    first 3200 bytes and the trace count only buys wall clock.

    Args:
        path: Where to write the file.
        n_inline: Inline count.
        n_crossline: Crossline count.
        n_samples: Samples per trace.

    Returns:
        The file, plus the conforming header it was derived from.
    """
    target = Path(path)
    article = make_poststack3d(
        target, n_inline=n_inline, n_crossline=n_crossline, n_samples=n_samples
    )
    conforming = article.textual_header

    payload = bytearray(target.read_bytes())
    for offset, value in PLANTED:
        payload[offset] = value
    target.write_bytes(bytes(payload))

    return UndecodableSegy(article=article, conforming_textual=conforming)
