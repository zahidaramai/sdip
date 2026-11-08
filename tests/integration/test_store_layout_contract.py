"""The store layout is a versioned contract (DECISIONS.md D-0141, GeoSuite F-SDIP-VER).

Commit ``cbb4f2d`` added the store array ``source_trace_ordinal`` while ``pyproject.toml`` stayed
at 1.6.0, and a reader's tests went red with no version to re-pin against. The P4 test already
listed the arrays, but it was edited in the next commit, so nothing tied the list to a version.

This module ties them. ``src/sdip/schema/sdip-store-layout.json`` declares, for each guarded
store shape, every node ``sdip ingest`` writes: its path, kind, Zarr ``data_type`` and its
``sdip*`` attribute keys, plus the root ``sdip*`` keys and the ``sdipStoreDigest`` keys. A real
ingest must produce exactly that. Changing it takes all of these together, or a test fails:

1. the manifest's ``shapes`` (what the store now holds);
2. a new ``history`` entry, under a version later than every earlier one, whose fingerprint is
   the new layout's;
3. that version in ``pyproject.toml`` (or earlier) and as a ``CHANGELOG.md`` heading;
4. :data:`RELEASED_FINGERPRINTS` below, extended (never edited) with the new entry;
5. ``STORE_CONTRACT.md`` naming every node and digest key.

Both halves (D-0088): the current store passes; an added array, a removed array, a retyped
array, a layout changed under an unchanged version, an unreleased version and a contract
document that omits a node each fail, in :func:`test_each_layout_corruption_is_caught`.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import shutil
import tomllib
from pathlib import Path
from typing import Any

import pytest
import zarr

from sdip.ingest import ingest
from tests.fixtures.generators import make_poststack3d

REPO = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO / "src" / "sdip" / "schema" / "sdip-store-layout.json"
CONTRACT_DOC = "STORE_CONTRACT.md"

RELEASED_FINGERPRINTS: dict[str, str] = {
    "1.6.0": "ef0dc586d25110257b102c316c4f6a43f648459305b272e541efbe1b8c49d01e",
    "1.7.0": "9405230edc62cd392fca7db766979d2db7fe1f3d9133fdc8af0ed9e539b8f46b",
}
"""Each release's layout fingerprint. **Append a version; never edit an existing value.**

A layout that changed under a released version would make every reader's pin a lie, which is
the defect this module exists to stop.
"""

SHAPES: dict[str, dict[str, Any]] = {
    "ibm32": {},
    "float32": {"sample_format": "float32"},
    "float32_delay": {"sample_format": "float32", "delay_recording_time": 100},
}
"""The guarded store shapes: the Appendix A.1 article as ``ibm32`` (it carries the raw sample
view), as IEEE ``float32`` (no raw view) and with a recording delay (the sample-axis origin)."""


def store_layout(store: str | Path) -> dict[str, Any]:
    """Read a store's layout with stock ``zarr`` and its own ``zarr.json`` files.

    Values are left out on purpose: a layout is which nodes exist and how they are typed, not
    what a survey holds. The ``data_type`` is the store's own JSON name (an extension's
    ``name``), so the layout does not depend on how a numpy version spells a dtype.
    """
    root = Path(store)
    group = zarr.open_group(str(root), mode="r")
    nodes = []
    for path, _node in sorted(group.members(max_depth=None)):
        meta = json.loads((root / path / "zarr.json").read_text())
        entry: dict[str, Any] = {
            "path": path,
            "kind": meta["node_type"],
            "sdip_attrs": sorted(k for k in meta.get("attributes", {}) if k.startswith("sdip")),
        }
        if meta["node_type"] == "array":
            data_type = meta["data_type"]
            entry["data_type"] = data_type if isinstance(data_type, str) else data_type["name"]
            entry["ndim"] = len(meta["shape"])
        nodes.append(entry)
    attrs = dict(group.attrs)
    marker = attrs.get("sdipStoreDigest") or {}
    return {
        "nodes": nodes,
        "root_sdip_attrs": sorted(k for k in attrs if k.startswith("sdip")),
        "store_digest_keys": sorted(marker),
    }


def fingerprint(shapes: dict[str, Any]) -> str:
    """SHA-256 of the canonical JSON of every guarded shape's layout."""
    canonical = json.dumps(shapes, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _version(text: str) -> tuple[int, ...]:
    if not re.fullmatch(r"\d+\.\d+\.\d+", text):
        raise ValueError(f"not a release version: {text!r}")
    return tuple(int(part) for part in text.split("."))


def layout_problems(
    manifest: dict[str, Any],
    *,
    changelog: str,
    package_version: str,
    released: dict[str, str],
    contract_doc: str,
) -> list[str]:
    """Every way the declared layout is not tied to a version and a contract. Empty means tied."""
    problems: list[str] = []
    history = manifest.get("history", {})
    current = manifest.get("layout_version", "")
    try:
        ordered = sorted(history, key=_version)
        current_v = _version(current)
        package_v = _version(package_version)
    except ValueError as exc:
        return [str(exc)]
    if not ordered or ordered[-1] != current:
        problems.append(f"layout_version {current} is not the latest history entry")
    if current_v > package_v:
        problems.append(
            f"layout_version {current} is ahead of the package version {package_version}"
        )
    if f"## [{current}]" not in changelog:
        problems.append(f"CHANGELOG.md has no heading for layout_version {current}")
    if current in history and history[current].get("fingerprint") != fingerprint(
        manifest["shapes"]
    ):
        problems.append(
            f"the declared layout changed but its fingerprint under {current} did not: a layout "
            "change needs a new version"
        )
    if sorted(history) != sorted(released):
        problems.append(f"history {sorted(history)} != released fingerprints {sorted(released)}")
    for version, value in released.items():
        if version in history and history[version].get("fingerprint") != value:
            problems.append(f"the fingerprint released under {version} was edited")
    fingerprints = [history[v].get("fingerprint") for v in ordered]
    if len(set(fingerprints)) != len(fingerprints):
        problems.append(
            "two history entries carry one fingerprint: a version with no layout change"
        )
    if current not in contract_doc:
        problems.append(f"{CONTRACT_DOC} does not name layout_version {current}")
    named: set[str] = set()
    for layout in manifest["shapes"].values():
        named |= {node["path"] for node in layout["nodes"]}
        named |= set(layout["store_digest_keys"])
    for name in sorted(named):
        if f"`{name}`" not in contract_doc:
            problems.append(f"{CONTRACT_DOC} does not name `{name}`")
    return problems


def _load_manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text())


def _repo_inputs() -> dict[str, Any]:
    pyproject = tomllib.loads((REPO / "pyproject.toml").read_text())
    return {
        "changelog": (REPO / "CHANGELOG.md").read_text(),
        "package_version": pyproject["project"]["version"],
        "released": RELEASED_FINGERPRINTS,
        "contract_doc": (REPO / CONTRACT_DOC).read_text(),
    }


@pytest.fixture(scope="module")
def stores(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """One real ingest per guarded shape, through the same code ``sdip ingest`` runs."""
    root = tmp_path_factory.mktemp("layout")
    out = {}
    for name, options in SHAPES.items():
        source = make_poststack3d(root / f"{name}.sgy", **options)
        ingest(source.path, root / f"{name}.mdio")
        out[name] = root / f"{name}.mdio"
    return out


# --- The pass half -------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_the_store_is_the_declared_layout(stores, shape):
    """A store array added, removed or retyped without a manifest change fails here."""
    declared = _load_manifest()["shapes"][shape]
    assert store_layout(stores[shape]) == declared, (
        f"sdip ingest's {shape} store no longer matches {MANIFEST_PATH.name}. A layout change "
        "needs a new version: see this module's docstring for the five things to change together."
    )


def test_the_layout_is_tied_to_a_version_and_a_contract():
    assert layout_problems(_load_manifest(), **_repo_inputs()) == []


def test_the_manifest_declares_exactly_the_guarded_shapes():
    assert sorted(_load_manifest()["shapes"]) == sorted(SHAPES)


def test_the_manifest_ships_with_the_package():
    """Readers can learn the layout from the installed package, not only from this checkout."""
    pyproject = tomllib.loads((REPO / "pyproject.toml").read_text())
    artifacts = pyproject["tool"]["hatch"]["build"]["targets"]["wheel"]["artifacts"]
    assert "src/sdip/schema/*.json" in artifacts


# --- The failing half (G7 discipline): each corruption must be caught ----------------------


def _add_array(store: Path) -> None:
    zarr.open_group(str(store), mode="r+").create_array("extra_array", shape=(1,), dtype="uint8")


def _remove_array(store: Path) -> None:
    shutil.rmtree(store / "source_trace_ordinal")


def _retype_array(store: Path) -> None:
    meta_path = store / "source_trace_ordinal" / "zarr.json"
    meta = json.loads(meta_path.read_text())
    meta["data_type"] = "int32"
    meta_path.write_text(json.dumps(meta))


@pytest.mark.integration
@pytest.mark.negative
@pytest.mark.parametrize("corrupt", [_add_array, _remove_array, _retype_array])
def test_a_changed_store_fails_the_layout(stores, tmp_path, corrupt):
    store = tmp_path / "copy.mdio"
    shutil.copytree(stores["float32"], store)
    assert store_layout(store) == _load_manifest()["shapes"]["float32"]  # baseline, same copy
    corrupt(store)
    assert store_layout(store) != _load_manifest()["shapes"]["float32"]


def _layout_changed_same_version(m: dict, r: dict) -> None:
    m["shapes"]["float32"]["nodes"].append(
        {"path": "extra", "kind": "array", "data_type": "uint8", "ndim": 1, "sdip_attrs": []}
    )


def _layout_changed_new_unreleased_version(m: dict, r: dict) -> None:
    _layout_changed_same_version(m, r)
    m["layout_version"] = "1.8.0"
    m["history"]["1.8.0"] = {"fingerprint": fingerprint(m["shapes"])}
    r["released"] = {**r["released"], "1.8.0": m["history"]["1.8.0"]["fingerprint"]}


def _released_fingerprint_edited(m: dict, r: dict) -> None:
    m["history"]["1.6.0"]["fingerprint"] = "0" * 64


def _version_with_no_layout_change(m: dict, r: dict) -> None:
    m["layout_version"] = "1.7.1"
    m["history"]["1.7.1"] = dict(m["history"]["1.7.0"])
    r["released"] = {**r["released"], "1.7.1": m["history"]["1.7.1"]["fingerprint"]}
    r["package_version"] = "1.7.1"
    r["changelog"] += "\n## [1.7.1]\n"


def _contract_doc_omits_a_node(m: dict, r: dict) -> None:
    r["contract_doc"] = r["contract_doc"].replace("`source_trace_ordinal`", "the ordinal array")


def _contract_doc_omits_a_digest_key(m: dict, r: dict) -> None:
    r["contract_doc"] = r["contract_doc"].replace("`contentV2`", "the second digest")


@pytest.mark.negative
@pytest.mark.parametrize(
    ("corrupt", "expected"),
    [
        (_layout_changed_same_version, "needs a new version"),
        (_layout_changed_new_unreleased_version, "ahead of the package version"),
        (_released_fingerprint_edited, "was edited"),
        (_version_with_no_layout_change, "no layout change"),
        (_contract_doc_omits_a_node, "`source_trace_ordinal`"),
        (_contract_doc_omits_a_digest_key, "`contentV2`"),
    ],
)
def test_each_layout_corruption_is_caught(corrupt, expected):
    manifest, inputs = copy.deepcopy(_load_manifest()), copy.deepcopy(_repo_inputs())
    assert layout_problems(manifest, **inputs) == []  # the baseline is clean
    corrupt(manifest, inputs)
    problems = layout_problems(manifest, **inputs)
    assert any(expected in problem for problem in problems), problems
