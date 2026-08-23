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
    "ci",
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
    workflows = list((repo_root / "ci").glob("*.yml"))
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


def test_all_four_firewall_layers_declare_the_same_set(repo_root):
    """A path protected by three layers and missed by the fourth is protected by three.

    The weakest layer is the real policy, so the sets must not drift. This fails a
    partial change rather than letting it ship a hole.
    """
    from sdip.cli.doctor import NEVER_PUBLISH

    gitignore = (repo_root / ".gitignore").read_text()
    hook = (repo_root / ".githooks" / "pre-commit").read_text()
    ci = (repo_root / "ci" / "ci.yml").read_text()
    firewall_job = ci.split("  firewall:", 1)[1].split("\n  fixture-policy:", 1)[0]

    for pattern in NEVER_PUBLISH:
        assert pattern in gitignore, f".gitignore is missing {pattern}"
        assert pattern in hook, f".githooks/pre-commit is missing {pattern}"
        assert pattern in firewall_job, f"CI firewall job is missing {pattern}"


def test_the_precommit_hook_exists_and_is_executable(repo_root):
    hook = repo_root / ".githooks" / "pre-commit"
    assert hook.is_file()
    assert hook.stat().st_mode & 0o111, "hook is not executable"
    assert hook.read_text().startswith("#!")


def test_the_precommit_hook_actually_blocks_a_staged_leak(tmp_path, repo_root):
    """NEGATIVE CONTROL. A hook nobody has watched fire is not a hook (SP11)."""
    import shutil

    _git(["init", "-q", "-b", "main"], tmp_path)
    _git(["config", "user.email", "t@example.invalid"], tmp_path)
    _git(["config", "user.name", "T"], tmp_path)
    hooks = tmp_path / ".githooks"
    hooks.mkdir()
    shutil.copy(repo_root / ".githooks" / "pre-commit", hooks / "pre-commit")
    (hooks / "pre-commit").chmod(0o755)
    _git(["config", "core.hooksPath", ".githooks"], tmp_path)

    (tmp_path / "CLAUDE.md").write_text("working context\n")
    _git(["add", "-f", "CLAUDE.md"], tmp_path)
    result = _git(["commit", "-m", "leak", "--no-gpg-sign"], tmp_path)

    assert result.returncode != 0, "the hook let a leak through"
    assert "BLOCKED" in (result.stdout + result.stderr)
    assert _git(["rev-parse", "HEAD"], tmp_path).returncode != 0, "a commit was created"


def test_doctor_reports_a_missing_hook_file(git_repo):
    """NEGATIVE CONTROL: no .githooks/pre-commit at all."""
    from sdip.cli.doctor import run_doctor

    hooks = next(c for c in run_doctor(git_repo).checks if c.name == "git-hooks")
    assert hooks.status.value == "FAIL"
    assert "missing" in hooks.summary


def test_doctor_reports_a_hook_that_is_present_but_not_installed(git_repo, repo_root):
    """NEGATIVE CONTROL: the file is there and `core.hooksPath` was never set.

    This is the state of every fresh clone, and it is the one a contributor is most
    likely to be in while believing they are protected.
    """
    import shutil

    from sdip.cli.doctor import run_doctor

    (git_repo / ".githooks").mkdir()
    shutil.copy(repo_root / ".githooks" / "pre-commit", git_repo / ".githooks" / "pre-commit")
    (git_repo / ".githooks" / "pre-commit").chmod(0o755)

    hooks = next(c for c in run_doctor(git_repo).checks if c.name == "git-hooks")
    assert hooks.status.value == "FAIL"
    assert "core.hooksPath" in hooks.summary


def test_doctor_reports_a_hook_that_is_not_executable(git_repo, repo_root):
    """NEGATIVE CONTROL: git silently ignores a non-executable hook."""
    import shutil

    from sdip.cli.doctor import run_doctor

    (git_repo / ".githooks").mkdir()
    shutil.copy(repo_root / ".githooks" / "pre-commit", git_repo / ".githooks" / "pre-commit")
    (git_repo / ".githooks" / "pre-commit").chmod(0o644)
    _git(["config", "core.hooksPath", ".githooks"], git_repo)

    hooks = next(c for c in run_doctor(git_repo).checks if c.name == "git-hooks")
    assert hooks.status.value == "FAIL"
    assert "not executable" in hooks.summary


def test_gitignore_has_no_negation_for_an_unpublishable_path(repo_root):
    """A single `!CLAUDE.md` line would defeat the whole firewall silently."""
    from sdip.cli.doctor import NEVER_PUBLISH

    lines = (repo_root / ".gitignore").read_text().splitlines()
    negations = [line for line in lines if line.startswith("!") and not line.startswith("!#")]
    for line in negations:
        assert not any(pattern in line for pattern in NEVER_PUBLISH), line


def test_every_gate_has_a_ci_job_that_arms_itself(repo_root):
    """Spec 7.8. Every gate is represented, and none blocks merge while unbuilt.

    An absent job renders as a green check, so the job must exist. A job that always
    fails blocks every PR forever, including the PR that would build it, so it must
    not fail while unbuilt. It therefore looks for its own subject and starts
    enforcing the moment that subject appears.
    """
    ci = (repo_root / "ci" / "ci.yml").read_text()
    for gate in (
        "integration",
        "negative-G7",
        "portability-G4",
        "spawn-guard",
        "determinism-G6",
    ):
        assert f"gate: {gate}" in ci, gate
    assert "steps.arm.outputs.armed" in ci, "gates must self-arm on their subject"
    assert "NOT_RUN" in ci


def test_unbuilt_gates_do_not_hard_fail_the_build(repo_root):
    """NEGATIVE CONTROL for the design above.

    A leftover `exit 1` in a gate job would silently reintroduce the always-red
    build that cannot be merged out of.
    """
    ci = (repo_root / "ci" / "ci.yml").read_text()
    gates_block = ci.split("  gates:", 1)[1].split("\n  roadmap:", 1)[0]
    assert "exit 1" not in gates_block


def test_firewall_is_enforced_in_ci_independently_of_doctor(repo_root):
    """The firewall job must not be gated on the environment being healthy.

    A broken environment is exactly when someone force-adds a file to make a check
    go away, so the job that catches it cannot itself depend on that environment.
    """
    ci = (repo_root / "ci" / "ci.yml").read_text()
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
    """SP9. One file per probe, at the repository root so it can be committed.

    They are **not** in ``docs/``: that is never committed (D-0010), and a
    pre-registration whose whole value is being publicly timestamped before the result
    exists cannot live where it can never be pushed. See D-0032.
    """
    prereg = repo_root / "prereg"
    assert prereg.is_dir(), "prereg/ must exist at the repository root"
    registered = {p.name.split("-")[0] for p in prereg.glob("P*.md")}
    assert {f"P{n}" for n in range(1, 9)} <= registered


def test_preregistrations_are_tracked(repo_root):
    """A pre-registration that is not in git is not a pre-registration.

    Git's commit timestamp is the entire mechanism: it is what distinguishes a
    commitment made before the run from a write-up composed after it.
    """
    if not (repo_root / ".git").exists():
        pytest.skip("not a git repository")
    result = _git(["ls-files", "prereg"], repo_root)
    tracked = {line.split("/")[-1] for line in result.stdout.splitlines() if line.strip()}
    for n in range(1, 9):
        assert any(f.startswith(f"P{n}-") for f in tracked), f"P{n} pre-reg is not tracked"


def test_certificate_schema_is_published(repo_root):
    """Spec 4.7 requires the schema published so a third party can validate without SDIP.

    It ships inside the package rather than in docs/, which is never committed. This
    asserts the file is tracked in the public tree - "published" means a reader can
    actually obtain it, not that it exists on someone's disk.
    """
    schema = repo_root / "src" / "sdip" / "schema" / "sdip-certificate-v0.schema.json"
    assert schema.is_file()
    result = _git(["ls-files", "--error-unmatch", str(schema.relative_to(repo_root))], repo_root)
    if "not a git repository" not in result.stderr:
        assert result.returncode == 0, "the schema exists but is not tracked"


def test_certificate_schema_loads_from_the_installed_package(repo_root):
    """`pip install sdip` must carry a validator for someone who never clones."""
    from sdip.schema import available_versions, load_schema

    assert available_versions() == ("0",)
    schema = load_schema()
    assert schema["title"] == "SDIP Equivalence Certificate v0"
    assert schema["$schema"].endswith("2020-12/schema")


def test_schema_encodes_the_rules_it_is_supposed_to_encode(repo_root):
    """The schema is not merely descriptive; several project rules are constraints.

    If one of these ever softens to a plain type, an invalid certificate becomes
    representable and the schema stops being a gate.
    """
    from sdip.schema import load_schema

    schema = load_schema()
    props = schema["properties"]
    assert props["spec_itemsize"]["const"] == 240
    assert props["spec_gap_free"]["const"] is True
    assert props["lossy_codec_present"]["const"] is False
    assert props["output_zarr_format"]["const"] == 3
    assert props["git"]["properties"]["dirty"]["const"] is False
    assert set(props["verdict"]["enum"]) == {
        "EQUIVALENT",
        "NON-EQUIVALENT",
        "PROVISIONAL",
    }


def test_equivalent_verdict_requires_its_evidence_in_the_same_document(repo_root):
    """There is no partial credit (spec 4.1), and the schema must enforce that."""
    from sdip.schema import load_schema

    conditional = load_schema()["allOf"][0]
    assert conditional["if"]["properties"]["verdict"]["const"] == "EQUIVALENT"
    then = conditional["then"]["properties"]
    for plane in ("plane_1", "plane_2", "plane_3", "plane_4", "plane_5"):
        assert then["planes"]["properties"][plane]["properties"]["status"]["const"] == "PASS"
    for gate in ("G1", "G2", "G7"):
        assert then["gates"]["properties"][gate]["const"] == "PASS"


def test_wheel_ships_the_schema(repo_root):
    """The firewall must not accidentally strip a runtime artifact from the build."""
    import tomllib

    data = tomllib.loads((repo_root / "pyproject.toml").read_text())
    artifacts = data["tool"]["hatch"]["build"]["targets"]["wheel"].get("artifacts", [])
    assert any("schema" in a and a.endswith(".json") for a in artifacts), artifacts
