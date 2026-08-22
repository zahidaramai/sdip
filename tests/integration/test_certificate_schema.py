"""The published certificate schema must accept a real certificate. Spec §4.7.

**This test should have existed from F2 and did not.** Its absence let the published
schema and the real output diverge silently for several phases: by the time it was
written, `issue()` emitted **eight** top-level keys and **five** `warnings` keys that the
schema's `additionalProperties: false` rejected outright.

Nothing failed. Every other test passed, `sdip certify` produced certificates, and the
schema sat in the package looking authoritative. §4.7's promise —

> The certificate schema is versioned independently and published so third parties can
> validate SDIP output **without running SDIP**.

— was false for anyone who tried, and only for them. **A published contract nobody checks
against the thing it describes is documentation, not a contract.**

`jsonschema` is a **dev** dependency. The runtime tree is licence-scanned and must not
grow: a consumer validating a certificate brings their own validator, which is the whole
point of publishing a schema rather than a library.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from sdip.equivalence import g4, issue, plane_1, plane_2, plane_3, plane_4, plane_5
from sdip.equivalence.closure import roundtrip_closure
from sdip.equivalence.determinism import g6
from sdip.equivalence.nonvacuity import g7
from sdip.equivalence.scale import g5
from sdip.export import export
from sdip.ingest import ingest
from sdip.schema import available_versions, load_schema
from tests.fixtures.generators import make_poststack3d

pytestmark = pytest.mark.integration

jsonschema = pytest.importorskip("jsonschema")


@pytest.fixture(scope="module")
def full_certificate(tmp_path_factory) -> dict[str, Any]:
    """A certificate from the **fullest** chain the engine can run.

    Deliberately the fullest: a sparse certificate would validate while leaving the
    optional blocks — the ones added most recently, and therefore the ones most likely
    to have diverged — completely unexercised.
    """
    root = tmp_path_factory.mktemp("cert")
    article = make_poststack3d(root / "src.sgy")
    store = root / "out.mdio"
    result = ingest(article.path, store)
    spec = result.spec.segy_spec

    planes = [
        plane_1(article.path, store),
        plane_2(article.path, store),
        plane_3(article.path, store, spec, g1_passed=True),
        plane_4(article.path, store, spec),
        plane_5(article.path, store, spec),
    ]
    exported = root / "back.sgy"
    roundtrip = export(store, exported, spec, source=article.path)

    certificate = issue(
        result,
        planes,
        roundtrip=roundtrip,
        portability=g4(store),
        nonvacuity=g7(article.path, store, spec, workdir=root / "g7"),
        closure=roundtrip_closure(exported, store, spec, workdir=root / "closure"),
        determinism=g6(article.path, 1, workdir=root / "g6"),
        scale=g5(
            peak_rss_bytes=1 << 30,
            wall_clock_s=1.0,
            trace_count=30,
            planes_passed=True,
            declared_rss_ceiling_bytes=8 * (1 << 30),
            declared_wall_ceiling_s=900.0,
            prereg_reference="tests/integration/test_certificate_schema.py",
        ),
        require_clean_tree=False,
        issued_at="2026-08-23T00:00:00Z",
        issued_by="test",
    )
    # `certify` refuses a dirty tree (§11.3), so any certificate that exists in the wild
    # was issued from a clean one. The fixture bypasses that to run at all, and must not
    # then claim the schema is wrong for enforcing it.
    payload = certificate.payload
    payload["git"] = dict(payload["git"]) | {"dirty": False}
    return payload


def test_a_real_certificate_validates_against_the_published_schema(full_certificate):
    """The guard whose absence let the schema rot.

    ``jsonschema`` reports every violation rather than the first, because a schema that
    has drifted usually drifts in several places at once and fixing them one error per
    run is how the drift got this far.
    """
    schema = load_schema()
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(full_certificate), key=lambda e: list(e.path))
    assert errors == [], "\n".join(
        f"  {'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}" for e in errors
    )


def test_the_schema_is_itself_a_valid_json_schema():
    """A malformed schema would make the test above vacuously pass."""
    jsonschema.Draft202012Validator.check_schema(load_schema())


def test_every_shipped_schema_version_validates(full_certificate):
    for version in available_versions():
        jsonschema.Draft202012Validator.check_schema(load_schema(version))


def test_the_equivalent_conditional_actually_bites(full_certificate):
    """NEGATIVE CONTROL: the schema's strongest claim must be enforceable.

    ``verdict: EQUIVALENT`` is required to imply all five planes PASS and G1/G2/G7 PASS.
    A conditional that never rejects anything is decoration.
    """
    schema = load_schema()
    validator = jsonschema.Draft202012Validator(schema)
    broken = dict(full_certificate)
    broken["verdict"] = "EQUIVALENT"
    broken["gates"] = dict(broken["gates"]) | {"G7": "NOT_RUN"}
    assert list(validator.iter_errors(broken)), (
        "the schema accepted EQUIVALENT with G7 NOT_RUN - the conditional is decoration"
    )


def test_a_lossy_codec_is_rejected_by_the_schema():
    """NEGATIVE CONTROL for SP3, at the schema layer."""
    schema = load_schema()
    validator = jsonschema.Draft202012Validator(schema)
    assert list(validator.iter_errors({"lossy_codec_present": True})), (
        "the schema accepted lossy_codec_present: true"
    )


def test_a_dirty_tree_is_rejected_by_the_schema():
    """NEGATIVE CONTROL for §11.3, at the schema layer."""
    schema = load_schema()
    validator = jsonschema.Draft202012Validator(schema)
    assert list(validator.iter_errors({"git": {"dirty": True}})), (
        "the schema accepted a certificate from a dirty tree"
    )


def test_certificates_on_disk_validate(repo_root: Path):
    """Any committed certificate must still validate. None exist yet; the guard does."""
    schema = load_schema()
    validator = jsonschema.Draft202012Validator(schema)
    import json

    for path in sorted((repo_root / "certificates").glob("*.json")):
        errors = list(validator.iter_errors(json.loads(path.read_text())))
        assert errors == [], f"{path.name}: {[e.message for e in errors]}"
