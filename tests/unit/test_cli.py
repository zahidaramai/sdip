"""CLI surface and the doctor report."""

from __future__ import annotations

import json
from typing import NoReturn

import pytest
from click.testing import CliRunner

from sdip.cli.doctor import run_doctor
from sdip.cli.main import EXIT_FAIL, cli
from sdip.cli.main import main as cli_entry
from sdip.cli.result import Status
from sdip.errors import (
    BarredEnvironmentError,
    DirtyTreeError,
    SdipError,
    SpecCompletenessError,
    UntrustedInputError,
)


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_all_six_commands_are_declared(runner):
    """Spec section 7 names six commands. All must exist, built or not."""
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    for command in ("doctor", "spec", "ingest", "verify", "export", "certify"):
        assert command in result.output


def test_every_command_is_now_built(runner):
    """F0-F3 built the whole surface. Nothing refuses with a phase any more.

    D-0008 said unbuilt commands refuse rather than stub. That rule has not changed -
    there is simply nothing left it applies to, and this test replaces the one that
    asserted the refusals so the change is visible in the diff rather than silent.
    """
    for args in (["spec", "build"], ["ingest"], ["verify"], ["export"], ["certify"]):
        result = runner.invoke(cli, [*args, "--help"])
        assert result.exit_code == 0, args
        assert "roadmap phase" not in result.output


def test_certify_help_states_the_real_bar_and_offers_no_override(runner):
    """`--help` must describe the bar as it is now, not as it was at F3.

    This test previously asserted "PROVISIONAL" appears, which was correct while G7 did
    not exist. G7 has existed since F4 and D11 is closed, so that assertion was pinning
    a claim that had become false - the help text told operators the tool was weaker than
    it is. It now pins the current bar: G7 runs, and `release_readiness` is stricter than
    the verdict.
    """
    output = runner.invoke(cli, ["certify", "--help"]).output
    assert "G7" in output
    assert "release_readiness" in output
    assert "NOT_RUN" in output
    assert "PROVISIONAL" not in output, "G7 exists; certify no longer caps out at PROVISIONAL"
    # The prose SAYS "there is no --force", which is the point - so the assertion
    # has to look at the Options block, not at the whole help text.
    options = output.split("Options:", 1)[1]
    for flag in ("--force", "--allow-dirty", "--skip", "--no-verify"):
        assert flag not in options


def test_doctor_runs_every_declared_check(repo_root):
    report = run_doctor(repo_root)
    assert [c.name for c in report.checks] == [
        "python-version",
        "barred-env-vars",
        "barred-packages",
        "upstream-pins",
        "runtime-licences",
        "working-tree",
        "publication-firewall",
        "git-hooks",
    ]


# Checks that report on the ENVIRONMENT rather than on the code. Neither is a defect
# in SDIP, and both legitimately fail in a correct setup: `working-tree` fails whenever
# anything is uncommitted, and `git-hooks` fails until someone runs
# `git config core.hooksPath .githooks`, which a fresh clone has not.
ENVIRONMENT_DEPENDENT: frozenset[str] = frozenset({"working-tree", "git-hooks"})


def test_doctor_substantive_checks_pass_here(repo_root):
    """Every check that judges the CODE must pass. Environment state may vary.

    **CORRECTED 2026-08-24, by CI's first-ever execution.** This asserted
    ``failing <= {"working-tree"}`` and passed on every developer machine, because a
    developer has run ``git config core.hooksPath .githooks`` at some point. A fresh CI
    checkout has not, so ``git-hooks`` failed and took the whole unit job with it.

    **The check was right and the test was wrong.** `sdip doctor` correctly reports that
    hooks are not installed in that job — the `doctor` job installs them explicitly
    before running, and `unit` has no reason to. What the test means to assert is that
    the checks judging SDIP itself pass: barred variables, barred packages, upstream
    pins, the licence scan and the publication firewall.

    The environment-dependent pair is named in :data:`ENVIRONMENT_DEPENDENT` rather than
    widened inline, so adding a third one is a deliberate act somebody has to justify.
    """
    report = run_doctor(repo_root)
    failing = {c.name for c in report.failed}
    assert failing <= ENVIRONMENT_DEPENDENT, [c.summary for c in report.failed]
    # and the substantive ones are asserted positively, not merely "not failing"
    passing = {c.name for c in report.checks if c.name not in failing}
    assert {
        "barred-env-vars",
        "barred-packages",
        "upstream-pins",
        "runtime-licences",
        "publication-firewall",
    } <= passing


def test_every_check_cites_a_clause(repo_root):
    """A check that cannot say what killed it is not a check."""
    for check in run_doctor(repo_root).checks:
        assert check.clause
        assert check.summary


def test_report_has_no_warn_status():
    """Gates are binary (spec 7). There is no WARN member to hide behind."""
    assert {s.name for s in Status} == {"PASS", "FAIL", "NOT_RUN"}


def test_doctor_json_is_machine_readable(runner, repo_root):
    result = runner.invoke(cli, ["doctor", "--json", "--root", str(repo_root)])
    payload = json.loads(result.output)
    assert payload["command"] == "doctor"
    assert payload["verdict"] in {"PASS", "FAIL"}
    assert len(payload["checks"]) == 8
    assert payload["environment"]["packages"]["multidimio"] == "1.2.1"


def test_doctor_exit_code_tracks_the_verdict(runner, repo_root):
    result = runner.invoke(cli, ["doctor", "--json", "--root", str(repo_root)])
    payload = json.loads(result.output)
    assert result.exit_code == (0 if payload["verdict"] == "PASS" else 1)


def test_doctor_has_no_override_flag(runner):
    """DECISIONS.md D-0007. No --force, no --allow-dirty, ever."""
    output = runner.invoke(cli, ["doctor", "--help"]).output
    for flag in ("--force", "--allow-dirty", "--skip", "--no-fail", "--ignore"):
        assert flag not in output


def test_dirty_tree_fails_doctor(git_repo):
    """NEGATIVE CONTROL: doctor must fail on a dirty tree."""
    (git_repo / "untracked.txt").write_text("x")
    report = run_doctor(git_repo)
    tree = next(c for c in report.checks if c.name == "working-tree")
    assert tree.status is Status.FAIL
    assert not report.ok


def test_clean_tree_passes_the_tree_check(git_repo):
    report = run_doctor(git_repo)
    tree = next(c for c in report.checks if c.name == "working-tree")
    assert tree.status is Status.PASS


@pytest.mark.parametrize(
    "path",
    [
        "docs/SDIP_Specification_v1.0.md",
        "docs/SDIP_Internal_Companion.md",
        "docs/prereg/P2-ibm32-fidelity.md",
        "CLAUDE.md",
        ".claude/settings.json",
        "AGENTS.md",
    ],
)
def test_firewall_fails_on_any_force_added_unpublishable_file(git_repo, path):
    """NEGATIVE CONTROL for the publication firewall.

    ``git add -f`` is the exact gesture that defeats .gitignore, so it is the gesture
    the check has to catch. This repository is public; a file tracked here is a file
    published.
    """
    import subprocess

    target = git_repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("not for publication\n")
    subprocess.run(["git", "add", "-f", path], cwd=git_repo, check=True)

    report = run_doctor(git_repo)
    firewall = next(c for c in report.checks if c.name == "publication-firewall")
    assert firewall.status is Status.FAIL
    assert path in firewall.evidence["tracked"]
    assert not report.ok


def test_firewall_catches_a_file_removed_from_the_index_but_left_in_history(git_repo):
    """NEGATIVE CONTROL: `git rm --cached` is not enough, and must not look like it.

    Removing a file from the index leaves it in every commit that already had it, and
    a clone receives history. The check inspects HEAD as well as the index precisely
    so this case cannot read as clean.
    """
    import subprocess

    (git_repo / "CLAUDE.md").write_text("working context\n")
    subprocess.run(["git", "add", "-f", "CLAUDE.md"], cwd=git_repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "oops", "--no-gpg-sign"], cwd=git_repo, check=True)
    subprocess.run(["git", "rm", "-q", "--cached", "CLAUDE.md"], cwd=git_repo, check=True)

    report = run_doctor(git_repo)
    firewall = next(c for c in report.checks if c.name == "publication-firewall")
    assert firewall.status is Status.FAIL, "index is clean but HEAD still carries it"
    assert "CLAUDE.md" in firewall.evidence["tracked"]


def test_firewall_passes_on_a_clean_repository(git_repo):
    report = run_doctor(git_repo)
    firewall = next(c for c in report.checks if c.name == "publication-firewall")
    assert firewall.status is Status.PASS


def test_version_flag_reports_the_specification_version(runner):
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "specification v1.0" in result.output


# ---------------------------------------------------------------------------
# `sdip spec build` — phase F1
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("revision", ["0", "1", "2", "2.1"])
def test_spec_build_passes_g1_for_every_revision(runner, revision):
    result = runner.invoke(cli, ["spec", "build", "--revision", revision])
    assert result.exit_code == 0, result.output
    assert "G1 PASS" in result.output
    assert "itemsize      240" in result.output


def test_spec_build_json_carries_the_certificate_block(runner):
    result = runner.invoke(cli, ["spec", "build", "--revision", "1", "--json"])
    payload = json.loads(result.output)
    assert payload["spec"]["spec_field_count"] == 97
    assert payload["spec"]["spec_itemsize"] == 240
    assert payload["spec"]["spec_gap_free"] is True
    assert len(payload["spec"]["spec_sha256"]) == 64
    assert payload["G1"]["status"] == "PASS"
    assert len(payload["G1"]["conditions"]) == 5


def test_spec_build_reports_fillers_honestly(runner):
    """Rev 2 needs none; saying "0 fillers" without saying why would read as a bug."""
    assert "already gap-free" in runner.invoke(cli, ["spec", "build", "--revision", "2"]).output
    assert "pad_233..pad_240" in runner.invoke(cli, ["spec", "build", "--revision", "1"]).output


def test_spec_build_rejects_an_unsupported_revision(runner):
    result = runner.invoke(cli, ["spec", "build", "--revision", "3"])
    assert result.exit_code != 0


def test_spec_build_is_deterministic(runner):
    """G6 starts here: the same revision must address the header identically."""
    first = json.loads(runner.invoke(cli, ["spec", "build", "--json"]).output)
    second = json.loads(runner.invoke(cli, ["spec", "build", "--json"]).output)
    assert first["spec"]["spec_sha256"] == second["spec"]["spec_sha256"]


class _BoomError(SdipError):
    """A deliberately-raised SDIP error that `main()` has never been told about."""


def test_every_sdip_error_reaches_the_operator_as_a_message_not_a_traceback(monkeypatch, capsys):
    """Section 3.6: a deliberate SDIP error is a clean error, never a crash.

    `main()` used to catch only `PhaseNotAuthorisedError`, so the other seven members of
    the `SdipError` family escaped the CLI boundary as raw tracebacks. That is worst for
    `UntrustedInputError` - SDIP parses binary files it did not create, and a traceback on
    a hostile SEG-Y is precisely the crash 3.6 bars.

    `_BoomError` is a subclass `main()` has never heard of, on purpose: the test asserts the
    boundary catches the **base class**, so a subclass written tomorrow is covered without
    anyone remembering to update a list.
    """
    for exc in (
        DirtyTreeError("tree is dirty"),
        UntrustedInputError("declared length exceeds the file"),
        SpecCompletenessError("byte 41 is uncovered"),
        BarredEnvironmentError("MDIO_IGNORE_CHECKS is set"),
        _BoomError("a subclass nobody enumerated"),
    ):

        def _raise(*_a: object, exc: SdipError = exc, **_k: object) -> NoReturn:
            raise exc

        monkeypatch.setattr(cli, "main", _raise)
        with pytest.raises(SystemExit) as caught:
            cli_entry()

        assert caught.value.code == EXIT_FAIL, f"{type(exc).__name__} must exit non-zero"
        err = capsys.readouterr().err
        assert "Traceback" not in err, f"{type(exc).__name__} leaked a traceback"
        assert type(exc).__name__ in err
        assert str(exc) in err
