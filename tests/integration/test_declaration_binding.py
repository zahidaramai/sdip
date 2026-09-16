"""A store records the declaration that wrote it; a different declaration is refused.

**Maintainer ruling (DECISIONS.md D-0087), from D47's root cause.** Ingest writes the
declaration's digest into the provenance marker. Every command that reads a store is
handed a declaration, builds its spec from that — never from the store's own record, so
the verifier does not trust the artifact under test to say how it should be read — and
compares digests. A mismatch is refused with both declarations named. A store written
before binding existed is ``UNBOUND``: still verifiable, and said so. A store SDIP did not
write is ``FOREIGN``.

MDIO's own ``name`` attribute records the template independently of SDIP's marker, so the
template is cross-checked even on stores SDIP did not write.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import zarr

from sdip.equivalence.binding import BOUND, FOREIGN, UNBOUND, check_binding
from sdip.errors import DeclarationMismatchError
from sdip.ingest import ingest
from sdip.ingest.provenance_marker import ATTR_DECLARATION
from sdip.spec import load_override, parse_override
from sdip.spec.declaration import SurveyDeclaration
from tests.fixtures.generators.revisions import make_revision_poststack3d

REPO = Path(__file__).resolve().parents[2]
REV0_OVERRIDE = REPO / "overrides" / "segy-rev0-poststack3d.toml"


@pytest.fixture(scope="module")
def rev0(tmp_path_factory):
    """One revision 0 store, ingested once with the committed rev 0 override."""
    work = tmp_path_factory.mktemp("binding")
    fixture = make_revision_poststack3d(work / "rev0.sgy", revision=0)
    override = load_override(REV0_OVERRIDE)
    declaration = SurveyDeclaration(revision=0, template="PostStack3DTime", override=override)
    ingest(fixture.path, work / "rev0.mdio", revision=0, override=override)
    return fixture, work / "rev0.mdio", declaration


def _copy(store: Path, tmp_path: Path) -> Path:
    target = tmp_path / "copy.mdio"
    shutil.copytree(store, target)
    return target


def _drop_attrs(store: Path, *names: str) -> None:
    group = zarr.open_group(str(store), mode="r+")
    attrs = dict(group.attrs)
    for name in names:
        attrs.pop(name, None)
    group.attrs.clear()
    group.attrs.update(attrs)


def test_ingest_records_the_declaration_it_was_given(rev0):
    _, store, declaration = rev0
    attrs = dict(zarr.open_group(str(store), mode="r").attrs)
    recorded = attrs[ATTR_DECLARATION]
    assert recorded["sha256"] == declaration.sha256()
    assert recorded["summary"] == declaration.summary()
    # MDIO's independent record of the template, which the binding also consults.
    assert attrs["name"] == declaration.template


def test_the_same_declaration_binds(rev0):
    _, store, declaration = rev0
    assert check_binding(store, declaration).status == BOUND


def test_a_different_declaration_is_refused_and_names_both(rev0):
    """The D47 shape: a rev 0 store read with verify's old defaults."""
    _, store, declaration = rev0
    wrong = SurveyDeclaration(revision=1, template="PostStack3DTime")
    with pytest.raises(DeclarationMismatchError) as caught:
        check_binding(store, wrong)
    message = str(caught.value)
    assert declaration.summary() in message
    assert wrong.summary() in message


def test_an_override_edited_without_a_version_bump_is_refused_and_says_so(rev0):
    _, store, declaration = rev0
    assert declaration.override is not None
    edited = parse_override(
        {
            "name": declaration.override.name,
            "version": declaration.override.version,
            "evidence": declaration.override.evidence + " Edited after ingest.",
            "field": [
                {"name": f.name, "byte": f.byte, "format": f.format}
                for f in declaration.override.fields
            ],
        }
    )
    same_name = SurveyDeclaration(revision=0, template="PostStack3DTime", override=edited)
    assert same_name.summary() == declaration.summary()
    with pytest.raises(DeclarationMismatchError, match="content"):
        check_binding(store, same_name)


def test_a_store_written_before_binding_is_unbound_not_refused(rev0, tmp_path):
    _, store, declaration = rev0
    copy = _copy(store, tmp_path)
    _drop_attrs(copy, ATTR_DECLARATION)
    result = check_binding(copy, declaration)
    assert result.status == UNBOUND
    assert result.recorded is None


def test_a_store_sdip_did_not_write_is_foreign(rev0, tmp_path):
    _, store, declaration = rev0
    copy = _copy(store, tmp_path)
    group_attrs = dict(zarr.open_group(str(copy), mode="r").attrs)
    _drop_attrs(copy, *[k for k in group_attrs if k.startswith("sdip")])
    assert check_binding(copy, declaration).status == FOREIGN


def test_the_template_is_checked_against_mdios_own_record_even_on_a_foreign_store(rev0, tmp_path):
    _, store, declaration = rev0
    copy = _copy(store, tmp_path)
    group_attrs = dict(zarr.open_group(str(copy), mode="r").attrs)
    _drop_attrs(copy, *[k for k in group_attrs if k.startswith("sdip")])
    depth = SurveyDeclaration(
        revision=0, template="PostStack3DDepth", override=declaration.override
    )
    with pytest.raises(DeclarationMismatchError, match="PostStack3DTime"):
        check_binding(copy, depth)


def test_the_binding_serialises_for_the_certificate(rev0):
    _, store, declaration = rev0
    block = check_binding(store, declaration).to_json()
    assert block["status"] == BOUND
    assert block["sha256"] == declaration.sha256()
    assert block["recorded_sha256"] == declaration.sha256()
    assert block["summary"] == declaration.summary()
