"""The repository's own contract: layout, records, and the rules that bind text.

These assert the parts of the specification that live in files rather than in code.
A refactor that quietly drops NOTICE attribution or a suppressed-warning ban is
exactly the kind of change that passes a normal test suite.
"""

from __future__ import annotations

import ast
import subprocess

import pytest

REQUIRED_PUBLIC_FILES = [
    "LICENSE",
    "NOTICE",
    "README.md",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "SECURITY.md",
    "CHANGELOG.md",
    "CITATION.cff",
    "DECISIONS.md",
    "EQUIVALENCE_LEDGER.md",
    "OPEN_DEBTS.md",
]

REQUIRED_DIRECTORIES = [
    ".github/workflows",
    "src/sdip/spec",
    "src/sdip/templates",
    "src/sdip/ingest",
    "src/sdip/export",
    "src/sdip/equivalence",
    "src/sdip/guard",
    "src/sdip/provenance",
    "src/sdip/cli",
    "tests/unit",
    "tests/integration",
    "tests/negative",
    "tests/fixtures",
    "certificates",
]


@pytest.mark.parametrize("name", REQUIRED_PUBLIC_FILES)
def test_required_public_file_exists(repo_root, name):
    """Spec section 6.2."""
    assert (repo_root / name).is_file()


@pytest.mark.parametrize("name", REQUIRED_PUBLIC_FILES)
def test_required_public_file_is_tracked(repo_root, name):
    """Present on disk is not the same as present in the repository.

    A machine-wide ``core.excludesFile`` ignoring CLAUDE.md is common enough that a
    contributor can pass every other check while the operating contract silently
    fails to ship. The repository .gitignore negates it; this asserts the negation
    works rather than trusting it.
    """
    import subprocess

    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", name],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if "not a git repository" in result.stderr:
        pytest.skip("not a git repository")
    assert result.returncode == 0, f"{name} exists on disk but is not tracked"


@pytest.mark.parametrize("name", REQUIRED_DIRECTORIES)
def test_required_directory_exists(repo_root, name):
    """Spec section 6.3."""
    assert (repo_root / name).is_dir()


def test_notice_carries_every_mandatory_attribution(repo_root):
    """Attribution in NOTICE is a legal obligation and must survive refactors."""
    notice = (repo_root / "NOTICE").read_text()
    for required in (
        "mdio-python",
        "TGSAI/mdio-python",
        "a2895b53088ffacbf4bd1b9e882856cbda78e235",
        "TGSAI/segy",
        "8e93e97db33ea4b2ce77433f6fdbef5d31ac6e78",
        "test_segy_roundtrip_teapot.py",
        "ThomasHertweck/seisio",
        "NO CODE FROM seisio HAS BEEN COPIED",
        "trhallam/segysak",
        "stuliveshere/pyseis-io",
    ):
        assert required in notice, required


def test_licence_is_apache_2(repo_root):
    licence = (repo_root / "LICENSE").read_text()
    assert "Apache License" in licence
    assert "Version 2.0, January 2004" in licence


def _suppression_calls(source: str) -> list[str]:
    """Return every real call that installs an ``ignore`` warnings filter.

    Parsed with ``ast`` rather than grepped, so the SP6 guard can quote upstream's
    suppression in a docstring and carry its regex as committed data - which it must,
    to classify a detected suppression - without tripping its own rule. Prose about a
    suppression is not a suppression; a call is.
    """
    offenders: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        name = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", "")
        if name not in {"filterwarnings", "simplefilter"}:
            continue
        literals = [a.value for a in node.args if isinstance(a, ast.Constant)]
        literals += [
            k.value.value
            for k in node.keywords
            if k.arg == "action" and isinstance(k.value, ast.Constant)
        ]
        if "ignore" in literals:
            offenders.append(f"{name} at line {node.lineno}")
    return offenders


def test_no_suppressed_warnings_anywhere_in_the_source(repo_root):
    """SP6. Never add ``warnings.filterwarnings("ignore", ...)``."""
    offenders = []
    for path in (repo_root / "src").rglob("*.py"):
        for call in _suppression_calls(path.read_text()):
            offenders.append(f"{path.relative_to(repo_root)}: {call}")
    assert offenders == []


def test_the_suppression_detector_actually_detects(tmp_path):
    """NEGATIVE CONTROL for the test above. A rule never shown to fire is not a rule."""
    assert _suppression_calls('import warnings\nwarnings.filterwarnings("ignore")\n')
    assert _suppression_calls('warnings.simplefilter("ignore")\n')
    assert _suppression_calls('warnings.filterwarnings(action="ignore")\n')
    # Prose and committed data must NOT trip it.
    assert not _suppression_calls('"""upstream calls filterwarnings(\'ignore\')."""\n')
    assert not _suppression_calls('REGEX = "ignore"\n')
    assert not _suppression_calls('warnings.simplefilter("always")\n')


TOLERANCE_CALLS = frozenset(
    {"allclose", "isclose", "assert_allclose", "assert_almost_equal", "approx"}
)
TOLERANCE_KWARGS = frozenset({"rtol", "atol"})


def _tolerance_uses(source: str) -> list[str]:
    """Return every real tolerance-based comparison in ``source``.

    Parsed, not grepped, for the same reason as the suppression detector: the engine's
    own docstrings must be able to say "no tolerance" without tripping the rule that
    says so.
    """
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name in TOLERANCE_CALLS:
            found.append(f"{name}() at line {node.lineno}")
        found.extend(
            f"{name}({kw.arg}=) at line {node.lineno}"
            for kw in node.keywords
            if kw.arg in TOLERANCE_KWARGS
        )
    return found


def test_no_tolerance_based_comparison_in_the_engine(repo_root):
    """Spec 4.5 / 9.5. A tolerance in the engine is a specification defect.

    The check runs over the whole source tree, not just ``equivalence/``, because a
    tolerance smuggled into a helper is the same defect at one remove.
    """
    offenders = []
    for path in (repo_root / "src").rglob("*.py"):
        for use in _tolerance_uses(path.read_text()):
            offenders.append(f"{path.relative_to(repo_root)}: {use}")
    assert offenders == []


def test_the_tolerance_detector_actually_detects():
    """NEGATIVE CONTROL for the test above."""
    assert _tolerance_uses("import numpy as np\nnp.allclose(a, b)\n")
    assert _tolerance_uses("np.testing.assert_allclose(a, b)\n")
    assert _tolerance_uses("np.array_equal(a, b, rtol=1e-9)\n")
    assert _tolerance_uses("compare(a, b, atol=0)\n")
    # Prose about tolerance is not tolerance.
    assert not _tolerance_uses('"""No allclose. Comparisons are array_equal."""\n')
    assert not _tolerance_uses("import numpy as np\nnp.array_equal(a, b)\n")


def test_barred_environment_variables_are_never_set_in_ci(repo_root):
    workflows = list((repo_root / ".github" / "workflows").glob("*.yml"))
    assert workflows, "CI workflows are a required public-project file"
    for path in workflows:
        text = path.read_text()
        for name in ("MDIO_IGNORE_CHECKS", "MDIO__IMPORT__RAW_HEADERS"):
            assert f"{name}:" not in text, f"{path.name} sets {name}"


def test_lossy_extra_is_not_declared(repo_root):
    """SP3 / spec 9.2. The lossy extra pulls zfpy and must not be requested.

    Parsed, not grepped: the pyproject comments name the extra precisely in order to
    say it is barred, and a rule that forbids naming the thing it forbids is a rule
    nobody can document.
    """
    import tomllib

    data = tomllib.loads((repo_root / "pyproject.toml").read_text())
    declared = list(data["project"]["dependencies"])
    for extra in data["project"].get("optional-dependencies", {}).values():
        declared.extend(extra)
    for group in data.get("dependency-groups", {}).values():
        declared.extend(group)
    for requirement in declared:
        assert "lossy" not in requirement, requirement
        assert "zfpy" not in requirement, requirement


def test_gitignore_covers_the_whole_firewall_set(repo_root):
    """First line of defence. The check on tracking is the last one."""
    from sdip.cli.doctor import NEVER_PUBLISH

    ignored = (repo_root / ".gitignore").read_text()
    for pattern in NEVER_PUBLISH:
        assert pattern in ignored, pattern


def test_append_only_records_declare_themselves(repo_root):
    for name in ("DECISIONS.md", "EQUIVALENCE_LEDGER.md", "OPEN_DEBTS.md"):
        text = (repo_root / name).read_text()
        assert "append-only" in text.lower(), name
        assert "SP10" in text, name


def test_open_debts_covers_every_appendix_b_entry(repo_root):
    """Debts are scheduled, never cancelled. None of D1-D8 may go missing."""
    text = (repo_root / "OPEN_DEBTS.md").read_text()
    for debt in [f"## D{n} " for n in range(1, 9)]:
        assert debt in text, debt


def test_g7_debt_is_recorded_explicitly(repo_root):
    """Until G7 passes, every certificate the engine issues is unvalidated."""
    text = (repo_root / "OPEN_DEBTS.md").read_text()
    assert "D11" in text
    assert "G7" in text


# ---------------------------------------------------------------------------
# Publication firewall. This repository is public.
#
# These are the highest-value tests in the file. Every other check protects data
# integrity; these protect against publishing material that was never meant to
# leave the working copy, which is the one failure that cannot be undone by a
# follow-up commit.
# ---------------------------------------------------------------------------


def _git(args, cwd) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)


def test_nothing_unpublishable_is_tracked(repo_root):
    """Nothing in NEVER_PUBLISH may be in the index or in HEAD."""
    from sdip.cli.doctor import tracked_unpublishable

    if not (repo_root / ".git").exists():
        pytest.skip("not a git repository")
    assert tracked_unpublishable(repo_root) == []


def test_nothing_unpublishable_appears_anywhere_in_history(repo_root):
    """A clone receives history, not just HEAD.

    ``git rm --cached`` removes a file from the index and leaves it in every commit
    that already contained it. Checking HEAD alone would pass while a clone still
    handed the reader the file.
    """
    from sdip.cli.doctor import NEVER_PUBLISH

    if not (repo_root / ".git").exists():
        pytest.skip("not a git repository")
    result = _git(
        [
            "log",
            "--all",
            "--pretty=format:",
            "--name-only",
            "--diff-filter=A",
            "--",
            *NEVER_PUBLISH,
        ],
        repo_root,
    )
    leaked = sorted({line for line in result.stdout.splitlines() if line.strip()})
    assert leaked == [], f"present in history; a clone would receive: {leaked}"


@pytest.mark.parametrize(
    "path",
    [
        "docs/SDIP_Specification_v1.0.md",
        "docs/SDIP_Internal_Companion.md",
        "docs/prereg/P2-ibm32-fidelity.md",
        "docs/certificate-schema/sdip-certificate-v0.schema.json",
        "CLAUDE.md",
        ".claude/settings.json",
        "AGENTS.md",
        ".claude-session-sync.md",
    ],
)
def test_every_unpublishable_path_is_ignored(repo_root, path):
    """NEGATIVE CONTROL: each path must match a .gitignore rule.

    ``--no-index`` is required: ``git check-ignore`` skips tracked files by default,
    so without it a file that is *already tracked* silently reports "not ignored" and
    the test would pass for the wrong reason.
    """
    if not (repo_root / ".git").exists():
        pytest.skip("not a git repository")
    result = _git(["check-ignore", "--no-index", "-q", "--", path], repo_root)
    assert result.returncode == 0, f"{path} is not covered by .gitignore"


def test_gitignore_has_no_negation_for_an_unpublishable_path(repo_root):
    """A single `!CLAUDE.md` line would defeat the whole firewall silently."""
    from sdip.cli.doctor import NEVER_PUBLISH

    lines = (repo_root / ".gitignore").read_text().splitlines()
    negations = [line for line in lines if line.startswith("!") and not line.startswith("!#")]
    for line in negations:
        assert not any(pattern in line for pattern in NEVER_PUBLISH), line


def test_firewall_is_enforced_in_ci_independently_of_doctor(repo_root):
    """The firewall job must not be gated on the environment being healthy.

    A broken environment is exactly when someone force-adds a file to make a check
    go away, so the job that catches it cannot itself depend on that environment.
    """
    ci = (repo_root / ".github" / "workflows" / "ci.yml").read_text()
    block = ci.split("  firewall:", 1)[1].split("\n  ", 1)[0]
    assert "needs: doctor" not in block
    assert "--all" in ci, "the firewall job must scan history, not only HEAD"


def test_sdist_does_not_ship_docs(repo_root):
    """The firewall must survive `uv build` as well as `git push`."""
    import tomllib

    data = tomllib.loads((repo_root / "pyproject.toml").read_text())
    include = data["tool"]["hatch"]["build"]["targets"]["sdist"]["include"]
    assert not any("docs" in entry for entry in include), include


# ---------------------------------------------------------------------------
# Local-only artifacts. Present on the working copy, never published.
# These skip in CI, where the working copy legitimately does not have them.
# ---------------------------------------------------------------------------


def test_every_probe_has_a_preregistration(repo_root):
    """SP9. Registered before the run, one file per probe. Local artifact."""
    prereg = repo_root / "docs" / "prereg"
    if not prereg.is_dir():
        pytest.skip("docs/ is not distributed; nothing to check in a published clone")
    registered = {p.name.split("-")[0] for p in prereg.glob("P*.md")}
    assert {f"P{n}" for n in range(1, 9)} <= registered


def test_certificate_schema_exists_locally(repo_root):
    """The schema is versioned and published separately, not from this repository."""
    schema_dir = repo_root / "docs" / "certificate-schema"
    if not schema_dir.is_dir():
        pytest.skip("docs/ is not distributed; nothing to check in a published clone")
    assert list(schema_dir.glob("*.schema.json"))
