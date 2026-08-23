"""**An `s3://` output must be refused, not silently redirected.** Spec §11.4, D7, P8.

Probe **P8** pointed SDIP at a real S3 server (MinIO on loopback) and asked it to write
there. What it measured:

* ``ingest(src, "s3://sdip-p8/via-sdip.mdio")`` returned **normally**, no exception, with
  ``IngestResult.output_path`` naming a local directory.
* ``sdip ingest src s3://sdip-p8/via-cli.mdio`` exited **0** and printed ``G1 PASS``.
* A complete 20-file store appeared under a local directory literally named ``s3:`` in the
  working directory — **49 paths** created.
* **0 objects** reached the bucket.

``Path("s3://bucket/key")`` collapses the doubled slash into the relative path
``s3:/bucket/key``, which resolves against the working directory. Nothing recognised the
scheme and nothing raised, so a successful-looking run and an empty bucket looked the same
to an operator. §11.4 bars a crash on bad input; it equally bars *"a write outside the
output path"*, and that is what this was. See ``DECISIONS.md`` D-0058.

**This suite tests the refusal, not object-store support.** Writing to an object store is
debt **D7** and is out of phase. Nothing here makes ``s3://`` work.

Three assertions per barred scheme, because two of them would pass on a broken fix:

1. It raises :class:`~sdip.errors.PhaseNotAuthorisedError` — typed, not a traceback.
2. The CLI exit code is non-zero and no traceback reaches stderr.
3. **Nothing is created in the working directory.** This is the assertion that actually
   pins the defect. A fix that raised *after* ``segy_to_mdio`` had run would satisfy 1 and
   2 and still leave the ``s3:`` tree on disk.

**The positive control is not decoration** (**SP11**, the same discipline as G7 and as the
D8 corpus). A validator that refused every path would score perfectly on 1-3 and be
useless, so real local paths — including a Windows drive letter and a POSIX directory with
a colon in its name — must be **accepted**.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from sdip.errors import PhaseNotAuthorisedError
from sdip.ingest import ingest, validate_output_path
from tests.fixtures.generators import make_poststack3d

pytestmark = [pytest.mark.negative]

BARRED = [
    "s3://bucket/store.mdio",
    "gs://bucket/store.mdio",
    "gcs://bucket/store.mdio",
    "az://container/store.mdio",
    "abfss://container@account.dfs.core.windows.net/store.mdio",
    "adl://account/store.mdio",
    "wasbs://container@account/store.mdio",
    "http://example.invalid/store.mdio",
    "https://example.invalid/store.mdio",
    "file:///tmp/store.mdio",
]
"""Every scheme is refused, so this list is evidence rather than configuration.

``file://`` is here deliberately: SDIP cannot write it either — ``Path("file:///tmp/x")``
is the relative path ``file:/tmp/x`` — and a rule that let one scheme through on the
grounds that it *sounds* local would reintroduce the defect for that one scheme.
"""

COLLAPSED = [
    # What `click.Path(path_type=Path)` hands to `ingest` after pathlib has already
    # collapsed the doubled slash. The CLI never delivers the `://` form, so a check
    # that only matched `://` would pass every test above and still leak from the CLI.
    "s3:/bucket/store.mdio",
    "gs:/bucket/store.mdio",
]

ACCEPTED = [
    "store.mdio",
    "./store.mdio",
    "../store.mdio",
    "/srv/surveys/store.mdio",
    "a/b/c/store.mdio",
    # A Windows drive letter is one character before the colon. A URI scheme is at least
    # two. Refusing this would be the same class of bug in the other direction.
    "C:/surveys/store.mdio",
    # A colon is a legal character in a POSIX directory name.
    "my:dir/store.mdio",
]


@pytest.mark.parametrize("target", BARRED + COLLAPSED)
def test_validator_refuses_every_uri_scheme(target):
    with pytest.raises(PhaseNotAuthorisedError) as raised:
        validate_output_path(target)
    message = str(raised.value)
    assert "D7" in message, "the refusal must name the debt it belongs to"
    assert "not implemented" in message.lower()


@pytest.mark.parametrize("target", ACCEPTED)
def test_validator_accepts_local_paths(target):
    """SP11. A gate that refuses everything distinguishes nothing and would be removed."""
    validate_output_path(target)
    validate_output_path(Path(target))


@pytest.mark.parametrize("target", BARRED)
def test_ingest_refuses_before_it_reads_the_source(tmp_path, target):
    """The refusal must beat source validation, which proves it runs before any work.

    The source here **does not exist**. If the output check ran after
    :func:`~sdip.ingest.validate_source`, this would raise ``UntrustedInputError`` about a
    missing file instead — a passing test for a check placed too late to prevent the
    write. §11.4 is an ordering requirement, so the ordering is what is asserted.
    """
    missing = tmp_path / "does-not-exist.sgy"
    with pytest.raises(PhaseNotAuthorisedError):
        ingest(missing, target)


def test_ingest_writes_nothing_when_it_refuses(tmp_path, monkeypatch):
    """The measured defect, asserted directly: no scheme-named directory, anywhere.

    ``monkeypatch.chdir`` matters. The leak resolved against the **working directory**, so
    a test run from the repository root would have created ``s3:`` at the repository root
    — which is how P8 found it in the first place.
    """
    source = make_poststack3d(tmp_path / "article.generated.sgy").path
    monkeypatch.chdir(tmp_path)
    before = sorted(p.name for p in tmp_path.iterdir())

    with pytest.raises(PhaseNotAuthorisedError):
        ingest(source, "s3://bucket/store.mdio")

    assert sorted(p.name for p in tmp_path.iterdir()) == before
    assert not (tmp_path / "s3:").exists(), "a directory named after the scheme was created"


def test_cli_refuses_with_a_nonzero_exit_and_leaves_the_cwd_untouched(tmp_path):
    """The whole defect through the shipped entry point, in one run.

    Exit **0** was the finding — an operator got a green run and an empty bucket. So the
    exit code, the absence of a traceback, and the state of the working directory are all
    asserted together; any one of them alone can be satisfied by a fix that is still wrong.
    """
    source = make_poststack3d(tmp_path / "article.generated.sgy").path
    work = tmp_path / "cwd"
    work.mkdir()

    proc = subprocess.run(
        [sys.executable, "-m", "sdip.cli", "ingest", str(source), "s3://bucket/store.mdio"],
        capture_output=True,
        text=True,
        cwd=str(work),
        timeout=300,
        check=False,
    )

    assert proc.returncode != 0, f"exit 0 is the defect; stdout was {proc.stdout!r}"
    assert "Traceback (most recent call last)" not in proc.stderr, proc.stderr[-500:]
    assert "D7" in proc.stderr or "D7" in proc.stdout
    assert list(work.iterdir()) == [], f"the CLI wrote {[p.name for p in work.iterdir()]}"
    assert "G1" not in proc.stdout, "no gate may report a verdict for a run that was refused"


def test_cli_still_ingests_to_a_local_path(tmp_path):
    """SP11 at the CLI boundary: the refusal must not have broken ordinary use."""
    source = make_poststack3d(tmp_path / "article.generated.sgy").path
    proc = subprocess.run(
        [sys.executable, "-m", "sdip.cli", "ingest", str(source), str(tmp_path / "out.mdio")],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
        timeout=600,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr[-800:]
    assert (tmp_path / "out.mdio").is_dir()
