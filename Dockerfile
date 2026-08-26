# SDIP — SEG-Y to MDIO/Zarr v3 with a machine-checkable Equivalence Certificate.
#
# Two stages. The builder resolves the LOCKED dependency set and compiles nothing into
# the runtime image; the runtime carries the interpreter, the package and its wheels and
# nothing else. `uv sync --frozen` is what makes the image reproducible: it installs the
# versions in `uv.lock`, so an image built today and one built next year hold the same
# `multidimio` and `segy`. That matters more here than in most projects, because a
# certificate issued under one decoder version says nothing about another.

FROM python:3.12-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:0.9.29 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

# Same path in both stages. uv writes ABSOLUTE shebangs into the venv's scripts, so a
# venv built at /build and copied to /opt breaks every console script in it - measured,
# not guessed: `exec /opt/sdip/.venv/bin/sdip: no such file or directory`.
WORKDIR /opt/sdip

# Dependency layer first, so a source-only change does not re-resolve the world.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project --no-dev --no-editable

COPY src/ ./src/
# --no-editable installs the package INTO site-packages. Without it uv installs it
# editable, pointing at /opt/sdip/src, which the runtime stage does not carry - the
# script then imports nothing: `ModuleNotFoundError: No module named 'sdip'`.
RUN uv sync --frozen --no-dev --no-editable


FROM python:3.12-slim-bookworm AS runtime

# Read by `sdip doctor`'s pin verification and printed on the certificate, so the labels
# and the artifact cannot drift apart.
LABEL org.opencontainers.image.title="SDIP" \
      org.opencontainers.image.description="Convert SEG-Y seismic data to MDIO/Zarr v3 with a machine-checkable proof the conversion changed nothing." \
      org.opencontainers.image.source="https://github.com/zahidaramai/sdip" \
      org.opencontainers.image.documentation="https://github.com/zahidaramai/sdip#readme" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.authors="Zahid Aramai" \
      org.opencontainers.image.vendor="Zahid Aramai"

# git is a runtime dependency, not a convenience: `sdip certify` refuses to issue from a
# dirty or absent working tree (spec 11.3), and `sdip doctor` reports on it. Without git
# the container can ingest and verify but cannot certify, which would be a silent
# capability gap rather than a stated one.
RUN apt-get update \
 && apt-get install --no-install-recommends -y git \
 && rm -rf /var/lib/apt/lists/*

# Non-root. The tool parses binary files it did not create (spec 3.6); it has no reason
# to hold more privilege than the data it reads.
RUN useradd --create-home --uid 10001 sdip
WORKDIR /work

COPY --from=builder --chown=sdip:sdip /opt/sdip/.venv /opt/sdip/.venv
ENV PATH="/opt/sdip/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER sdip

# `--help` exits 0 and touches no filesystem, so the healthcheck cannot be confused by an
# empty or read-only mount.
HEALTHCHECK --interval=30s --timeout=10s --retries=3 CMD ["sdip", "--help"]

ENTRYPOINT ["sdip"]
CMD ["--help"]
