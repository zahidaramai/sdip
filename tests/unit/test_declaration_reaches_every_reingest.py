"""No path inside SDIP can fall back to a default reading. OPEN_DEBTS D62.

D47 threaded the survey declaration through the commands. D62 found the one path it did
not reach: the round-trip closure re-ingested ``certify``'s export under parameters that
defaulted to revision 1 and ``PostStack3DTime``, and nothing noticed, because nothing
required the declaration to be passed. Looking for the rest of that class found two more
of the same shape - a declaration handed over in pieces, so one piece could stay behind:
the hostile-input preflight took the byte order and the revision as defaulted keywords
(how D28 regressed), and Plane 2's revision check took the revision and never the byte
order. Structural guards make the class unwritable rather than untested:

1. every function that reads, re-reads or records on the operator's behalf takes
   ``declaration`` as a required parameter, and none keeps a piece of the reading - a
   revision, a template, an override, a byte order, a spec - as a parameter of its own;
2. a function that may run without one (Plane 2, as G7 runs it) still takes it whole;
3. the ingest takes the declaration and never takes it apart: the keyword form builds one
   and hands it on, not the other way round;
4. no module outside ``sdip.ingest`` reaches the defaulted keyword forms - ``ingest`` and
   ``validate_segy_structure`` - by import or by call.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from sdip.equivalence.closure import roundtrip_closure
from sdip.equivalence.determinism import g6
from sdip.equivalence.nonvacuity import closure_control
from sdip.equivalence.planes import plane_2
from sdip.ingest import ingest_declared, validate_source
from sdip.ingest.provenance_marker import attach_provenance_marker, marker_attrs

SRC = Path(__file__).resolve().parents[2] / "src" / "sdip"
LOOSE_READING_PARAMETERS = {
    "revision",
    "spec_revision",
    "declared_revision",
    "template",
    "override",
    "grid_overrides",
    "endianness",
    "spec",
    "segy_spec",
}
"""Pieces of a reading. A function that holds the declaration has no use for any of them."""

DECLARATION_REQUIRED = [
    roundtrip_closure,
    closure_control,
    g6,
    ingest_declared,
    validate_source,
    attach_provenance_marker,
    marker_attrs,
]
DEFAULTED_KEYWORD_FORMS = {"ingest", "validate_segy_structure"}
"""Functions whose reading parameters default. Legitimate inside ``sdip.ingest`` only."""


@pytest.mark.parametrize("function", DECLARATION_REQUIRED, ids=lambda f: f.__name__)
def test_the_declaration_is_required(function):
    declaration = inspect.signature(function).parameters["declaration"]
    assert declaration.default is inspect.Parameter.empty, f"{function.__name__} defaults it"


@pytest.mark.parametrize("function", [*DECLARATION_REQUIRED, plane_2], ids=lambda f: f.__name__)
def test_the_declaration_is_the_only_reading_parameter(function):
    parameters = set(inspect.signature(function).parameters)
    assert "declaration" in parameters
    assert not LOOSE_READING_PARAMETERS & parameters, (
        f"{function.__name__} takes part of the reading separately: "
        f"{sorted(LOOSE_READING_PARAMETERS & parameters)}"
    )


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    [node] = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name]
    return node


def _calls(node: ast.AST) -> set[str]:
    names = set()
    for call in (n for n in ast.walk(node) if isinstance(n, ast.Call)):
        func = call.func
        names.add(func.id if isinstance(func, ast.Name) else getattr(func, "attr", ""))
    return names


def test_the_ingest_never_takes_the_declaration_apart():
    """``ingest`` builds a declaration and calls ``ingest_declared`` - never the reverse.

    The reverse - unpacking a declaration into ``ingest``'s keywords, which rebuild it - is
    two lists of fields to keep in step, and a field missing from either one is a store
    written under a reading nobody declared.
    """
    tree = ast.parse((SRC / "ingest" / "orchestrator.py").read_text())
    declared, keyword_form = _function(tree, "ingest_declared"), _function(tree, "ingest")
    assert "SurveyDeclaration" not in _calls(declared), "ingest_declared rebuilds a declaration"
    assert "ingest" not in _calls(declared), "ingest_declared unpacks into the keyword form"
    assert {"SurveyDeclaration", "ingest_declared"} <= _calls(keyword_form)


def _offenders(source: str, where: str) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(source, filename=where)):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("sdip.ingest"):
            found += [
                f"{where}:{node.lineno} imports {alias.name}"
                for alias in node.names
                if alias.name in DEFAULTED_KEYWORD_FORMS
            ]
        elif isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if name in DEFAULTED_KEYWORD_FORMS:
                found.append(f"{where}:{node.lineno} calls {name}")
    return found


def test_no_module_outside_the_ingest_package_reaches_a_defaulted_keyword_form():
    offenders = []
    for path in sorted(SRC.rglob("*.py")):
        if path.parent == SRC / "ingest":
            continue
        offenders += _offenders(path.read_text(), str(path.relative_to(SRC)))
    assert offenders == [], f"hold a declaration and pass it whole instead: {offenders}"


@pytest.mark.parametrize(
    "sample",
    [
        "from sdip.ingest import ingest as run_ingest\n",
        "from sdip.ingest.orchestrator import ingest\n",
        "import sdip.ingest\nsdip.ingest.ingest(source, output)\n",
        "from sdip.ingest import orchestrator\norchestrator.ingest(source, output, revision=0)\n",
        "from sdip.ingest.preflight import validate_segy_structure\n",
        "preflight.validate_segy_structure(path, size)\n",
    ],
)
def test_the_guard_can_see_an_offender(sample):
    """The scan above must be able to fail. An AST walk that matches nothing is not a guard."""
    assert _offenders(sample, "sample.py")


@pytest.mark.parametrize(
    "sample",
    [
        "from sdip.ingest import ingest_declared\ningest_declared(source, output, declaration)\n",
        "from sdip.ingest.orchestrator import validate_source\nvalidate_source(p, declaration)\n",
        '@cli.command("ingest")\ndef ingest_cmd(): ...\n',
    ],
)
def test_the_guard_passes_the_declared_forms(sample):
    """And it must not fire on the calls it exists to steer towards."""
    assert _offenders(sample, "sample.py") == []
