"""Allow ``python -m sdip.cli``.

The ``__main__`` guard is not decoration. MDIO's header parser uses a ``spawn``
multiprocessing context; without the guard the child re-executes the ingest and the
pool dies with ``BrokenProcessPool`` (spec 11.1, Appendix A.5). A CI job invokes
ingestion as a script to catch a regression here.
"""

from __future__ import annotations

from sdip.cli.main import main

if __name__ == "__main__":
    main()
