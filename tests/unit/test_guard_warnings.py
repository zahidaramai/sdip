"""Guard: SP6 warning ledger.

These tests pin the *measured* behaviour recorded in DECISIONS.md D-0004 against the
binding pins. If a pin bump changes any of it, these fail — which is the point.
"""

from __future__ import annotations

import logging
import subprocess
import sys
import warnings

import pytest

from sdip.guard.warn import (
    KNOWN_UPSTREAM_SUPPRESSIONS,
    LEDGER_SCOPE,
    MAX_STDERR_RECORDS,
    WARNING_TEXT_LINE,
    WarningLedger,
    recording_log_records,
    recording_warnings,
    recovering_worker_stderr,
)


def test_observable_warnings_are_recorded():
    with recording_warnings(reemit=False) as ledger:
        warnings.warn("observable", UserWarning, stacklevel=1)
    assert [w.message for w in ledger.observed] == ["observable"]
    assert ledger.observed[0].category == "UserWarning"


def test_recorder_is_not_a_swallower():
    """The default re-emits, preserving the exact category and origin."""
    with pytest.warns(DeprecationWarning, match="passed through"):
        with recording_warnings() as ledger:
            warnings.warn("passed through", DeprecationWarning, stacklevel=1)
    assert [w.category for w in ledger.observed] == ["DeprecationWarning"]


def test_warnings_are_not_deduplicated():
    """A warning raised once per trace must be counted once per trace."""
    with recording_warnings(reemit=False) as ledger:
        for _ in range(5):
            warnings.warn("same message", UserWarning, stacklevel=1)
    assert len(ledger.observed) == 5


def test_upstream_suppression_is_detected_and_declared():
    """MEASURED, D-0004. Entering the upstream CM installs a filter SDIP records."""
    from mdio.core.zarr_io import zarr_warnings_suppress_unstable_structs_v3

    with recording_warnings(reemit=False) as ledger:
        with zarr_warnings_suppress_unstable_structs_v3():
            pass

    installed = ledger.suppressions_installed
    assert len(installed) == 1
    assert installed[0].action == "ignore"
    assert installed[0].category == "UnstableSpecificationWarning"
    assert installed[0].known_id == "mdio-1.2.1-unstable-structs-v3"
    assert installed[0].declared
    assert ledger.undeclared_suppressions == []


def test_an_undeclared_suppression_is_flagged():
    """NEGATIVE CONTROL: a suppression SDIP has not read must be flagged UNDECLARED.

    This is the change-detector for a pin bump that introduces a new suppression.
    """
    with recording_warnings(reemit=False) as ledger:
        warnings.filterwarnings(
            "ignore", message="a suppression nobody declared", category=FutureWarning
        )

    assert len(ledger.undeclared_suppressions) == 1
    flagged = ledger.undeclared_suppressions[0]
    assert flagged.known_id is None
    assert flagged.to_json()["status"] == "UNDECLARED"


def test_the_upstream_global_leak_is_contained():
    """MEASURED, D-0004 / OPEN_DEBTS D10.

    Upstream's context managers use filterwarnings without catch_warnings and end in
    `finally: pass`, so the ignore filter leaks process-globally. SDIP must not leave
    the interpreter quieter than it found it.
    """
    from mdio.core.zarr_io import (
        zarr_warnings_suppress_unstable_numcodecs_v3,
        zarr_warnings_suppress_unstable_structs_v3,
    )

    before = len(warnings.filters)
    with recording_warnings(reemit=False):
        with zarr_warnings_suppress_unstable_structs_v3():
            pass
        with zarr_warnings_suppress_unstable_numcodecs_v3():
            pass
    assert len(warnings.filters) == before


def test_upstream_really_does_leak_without_the_guard():
    """NEGATIVE CONTROL for the test above.

    If upstream ever scopes its filters correctly this fails, and the containment
    claim in D-0004 must be re-read rather than assumed still necessary.
    """
    from mdio.core.zarr_io import zarr_warnings_suppress_unstable_structs_v3

    with warnings.catch_warnings():  # restores state for the rest of the suite
        before = len(warnings.filters)
        with zarr_warnings_suppress_unstable_structs_v3():
            pass
        assert len(warnings.filters) == before + 1, (
            "upstream no longer leaks; re-read DECISIONS.md D-0004"
        )


def test_suppressed_warnings_are_genuinely_unobservable():
    """MEASURED, D-0004. Documents why SP6 is detection, not re-raising.

    An outer always+record observes zero suppressed warnings. If this ever starts
    passing warnings through, the SP6 implementation can be simplified — and this
    test failing is how anyone would find out.
    """
    from mdio.core.zarr_io import zarr_warnings_suppress_unstable_structs_v3
    from zarr.errors import UnstableSpecificationWarning

    with recording_warnings(reemit=False) as ledger:
        with zarr_warnings_suppress_unstable_structs_v3():
            warnings.warn(
                "The data type (struct) does not have a Zarr V3 specification.",
                UnstableSpecificationWarning,
                stacklevel=1,
            )
    assert ledger.observed == []


def test_known_suppressions_are_pinned_to_a_pinned_version():
    """Every declared filter names the package, version and site it was read from.

    The set spans three packages: multidimio suppresses, and xarray and numcodecs
    deduplicate. All three mutate global warning state, so all three are declared.
    """
    packages = {e["package"] for e in KNOWN_UPSTREAM_SUPPRESSIONS}
    assert packages == {"multidimio", "xarray", "numcodecs"}
    for entry in KNOWN_UPSTREAM_SUPPRESSIONS:
        assert entry["version"]
        assert entry["site"]
        assert entry["message_regex"]


def test_deduplication_is_not_reported_as_suppression():
    """`once` shows the first occurrence. Calling that a suppression cries wolf."""
    import warnings

    from sdip.guard.warn import recording_warnings

    with recording_warnings(reemit=False) as ledger:
        warnings.filterwarnings("once", message="a dedup filter", category=FutureWarning)
    installed = ledger.suppressions_installed
    assert len(installed) == 1
    assert installed[0].kind == "deduplication"
    assert installed[0].suppresses is False
    assert ledger.suppressions == []
    assert ledger.undeclared_suppressions == []
    assert len(ledger.undeclared_filters) == 1


def test_known_suppression_regexes_match_the_installed_source():
    """The committed regexes must be the ones actually in the pinned source."""
    import inspect

    import mdio.core.zarr_io as zarr_io

    source = inspect.getsource(zarr_io)
    for entry in KNOWN_UPSTREAM_SUPPRESSIONS:
        if entry["site"].startswith("mdio/core/zarr_io.py"):
            assert entry["message_regex"] in source, entry["id"]


def test_ledger_serialises_for_a_certificate():
    ledger = WarningLedger()
    with recording_warnings(ledger, reemit=False):
        pass
    payload = ledger.to_json()
    assert payload["observed_count"] == 0
    assert payload["undeclared_suppression_count"] == 0
    assert len(payload["known_upstream_suppressions"]) == len(KNOWN_UPSTREAM_SUPPRESSIONS)
    assert "monkeypatching" in payload["sp6_scope_note"]


# --------------------------------------------------------------------------------------
# Blind spot 2 — `logger.warning` is not a Python warning. OPEN_DEBTS D26.
# --------------------------------------------------------------------------------------


def test_a_log_record_is_recorded():
    """The channel `catch_warnings` cannot see, by construction."""
    with recording_log_records() as ledger:
        logging.getLogger("upstream.grid_qc").warning("Ingestion grid is sparse. %s", 3.0)

    assert len(ledger.logged) == 1
    record = ledger.logged[0]
    assert record.logger == "upstream.grid_qc"
    assert record.level == "WARNING"
    assert record.levelno == logging.WARNING
    assert record.message == "Ingestion grid is sparse. 3.0"
    assert record.module == "test_guard_warnings"


def test_the_two_channels_are_not_merged():
    """A warning and a log record are different mechanisms and stay in different lists.

    Only one of the two is suppressible by a filter. Flattening them would report the
    wrong mechanism for half the entries, and the mechanism is the point.
    """
    ledger = WarningLedger()
    with recording_warnings(ledger, reemit=False), recording_log_records(ledger):
        warnings.warn("through the warnings module", UserWarning, stacklevel=1)
        logging.getLogger("upstream").warning("through the logging module")

    assert [w.message for w in ledger.observed] == ["through the warnings module"]
    assert [r.message for r in ledger.logged] == ["through the logging module"]

    payload = ledger.to_json()
    assert payload["observed_count"] == 1
    assert payload["logged_count"] == 1


def test_records_below_the_threshold_are_not_recorded():
    """WARNING and above. SP6 is about warnings, not about upstream's INFO chatter."""
    with recording_log_records() as ledger:
        logging.getLogger("upstream").info("routine progress")
        logging.getLogger("upstream").error("a real problem")

    assert [r.level for r in ledger.logged] == ["ERROR"]


def test_the_handler_is_removed_even_when_the_block_raises():
    """This module must not leak global state, which is what it criticises upstream for."""
    root = logging.getLogger()
    before = list(root.handlers)

    with pytest.raises(RuntimeError, match="from inside the block"):
        with recording_log_records():
            assert len(root.handlers) == len(before) + 1
            raise RuntimeError("from inside the block")

    assert root.handlers == before


def test_the_recorder_does_not_silence_a_bare_root_logger(repo_root):
    """MEASURED. The recorder must not quieten the run it is measuring.

    ``Logger.callHandlers`` falls back to ``logging.lastResort`` — which prints to
    stderr — only when it finds **no** handler in the chain. SDIP configures no logging
    and neither does MDIO, so during an ingest that fallback is the only thing putting
    upstream's warnings on the terminal. Attaching any handler displaces it.

    Run in a subprocess because pytest's own logging plugin attaches a handler to the
    root logger, so the condition being measured — a genuinely bare root logger, which
    is what `sdip ingest` actually has — cannot exist inside a test process.
    """
    recorded = subprocess.run(
        [
            sys.executable,
            "-c",
            "import logging\n"
            "from sdip.guard.warn import recording_log_records\n"
            "with recording_log_records() as ledger:\n"
            "    logging.getLogger('upstream').warning('SENTINEL')\n"
            "assert [r.message for r in ledger.logged] == ['SENTINEL']\n",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "SENTINEL" in recorded.stderr, (
        "the recorder swallowed a message that would otherwise have reached stderr"
    )


def test_a_plain_handler_really_does_silence_a_bare_root_logger(repo_root):
    """NEGATIVE CONTROL for the test above.

    Same subprocess, same log call, a recorder that does *not* carry the displaced
    fallback. If this ever starts printing, ``lastResort`` no longer works the way the
    test above depends on and the re-emission can be reconsidered — this failing is how
    anyone would find out.
    """
    silenced = subprocess.run(
        [
            sys.executable,
            "-c",
            "import logging\n"
            "class Silent(logging.Handler):\n"
            "    def emit(self, record): pass\n"
            "logging.getLogger().addHandler(Silent(level=logging.WARNING))\n"
            "logging.getLogger('upstream').warning('SENTINEL')\n",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "SENTINEL" not in silenced.stderr, (
        "lastResort is no longer displaced by an attached handler; re-read "
        "recording_log_records, whose re-emission exists only for that"
    )


# --------------------------------------------------------------------------------------
# Blind spot 1 — narrowed. Text is recovered; the warning object is still gone.
# OPEN_DEBTS D35.
# --------------------------------------------------------------------------------------


def test_the_ledger_declares_its_own_scope():
    """An empty `observed` must stop reading as evidence of a quiet run.

    **These strings are the claim.** A change that genuinely captures worker warnings as
    *objects* has to edit this assertion, which is deliberate: the capability and the
    claim land in the same commit or neither does.
    """
    scope = WarningLedger().to_json()["scope"]

    covers = (
        "parent-process Python warnings, parent-process log records, and warning-shaped "
        "text recovered from file descriptor 2 during the guarded call"
    )
    assert scope["covers"] == covers
    assert "NOT CAPTURED AS WARNING OBJECTS" in scope["worker_process_warnings"]
    assert scope["worker_process_log_records"] == "NOT CAPTURED - see OPEN_DEBTS D35"
    assert "spawn pool" in scope["empty_observed_means"]
    assert "monkeypatching" in scope["why_workers_are_not_captured"]


def test_the_scope_is_machine_checkable_not_only_prose():
    """D35's narrowing. A consumer must be able to TEST for the gap, not read for it.

    Prose on a certificate is read by whoever thought to read it. These booleans are the
    part a downstream validator can assert on, and each has exactly one meaning:
    ``worker_warnings_captured`` is what SP6 would need and does not have;
    ``worker_stderr_text_recovered`` is the weaker thing that was actually built.
    """
    scope = WarningLedger().to_json()["scope"]

    assert scope["worker_warnings_captured"] is False
    assert scope["worker_log_records_captured"] is False
    assert scope["log_records_below_effective_level_captured"] is False
    # A fresh ledger watched nothing, and says so rather than implying a quiet run.
    assert scope["worker_stderr_text_recovered"] is False
    assert scope["worker_stderr_bytes_scanned"] == 0
    assert scope["worker_stderr_recovery_truncated"] is False


def test_worker_warnings_captured_is_a_literal_false():
    """The flag must not be inferrable from the recovery that DOES work.

    Text recovery is strictly weaker than warning capture, and the failure mode this
    guards against is a later change wiring ``worker_warnings_captured`` to
    ``stderr_watched`` and thereby claiming SP6 coverage the project does not have.
    """
    ledger = WarningLedger(stderr_watched=True, stderr_bytes_scanned=4096)
    scope = ledger.to_json()["scope"]

    assert scope["worker_stderr_text_recovered"] is True
    assert scope["worker_warnings_captured"] is False


def test_the_scope_names_the_sites_that_were_searched():
    """SP8: the "no hook exists" finding is a measurement, and names what was measured.

    The version-specific line numbers are the evidence. A pin bump moves them, and
    whoever bumps the pin has to look again rather than inherit the conclusion.
    """
    why = LEDGER_SCOPE["why_workers_are_not_captured"]
    for site in ("mdio/segy/blocked_io.py:104", "mdio/segy/parsers.py:61"):
        assert site in why
    assert "spec 3.3" in why
    # Every MDIOSettings field, so "there is no worker callback" is checkable rather
    # than asserted. Two of the eight are barred by spec 9.1 and named as such.
    for setting in ("cloud_native", "export_cpus", "import_cpus", "save_segy_file_header"):
        assert setting in why


def test_a_warning_printed_by_a_child_process_is_recovered(tmp_path):
    """MEASURED, and the point of the whole exercise.

    A subprocess is the honest stand-in for an MDIO ``spawn`` worker: a different
    interpreter whose ``warnings`` machinery this process cannot reach, sharing only the
    inherited file descriptor. The recovered record proves the text is reachable when
    the object is not.
    """
    ledger = WarningLedger()
    with recovering_worker_stderr(ledger):
        subprocess.run(
            [
                sys.executable,
                "-c",
                "import warnings\n"
                "warnings.warn('from another interpreter', RuntimeWarning, stacklevel=1)\n",
            ],
            check=True,
        )

    assert ledger.stderr_watched is True
    recovered = [r for r in ledger.stderr_recovered if "another interpreter" in r.message]
    assert len(recovered) == 1, [r.message for r in ledger.stderr_recovered]
    assert recovered[0].category == "RuntimeWarning"
    assert recovered[0].lineno == 2


def test_the_tee_does_not_swallow_what_it_reads(tmp_path, capfd):
    """SP6's own discipline: a recorder must not leave the process quieter.

    The bytes must reach the real descriptor unchanged. If they did not, SDIP would be
    silencing the run it is measuring — exactly what it criticises upstream for.
    """
    ledger = WarningLedger()
    with recovering_worker_stderr(ledger):
        subprocess.run(
            [sys.executable, "-c", "import sys; sys.stderr.write('SENTINEL-VISIBLE\\n')"],
            check=True,
        )

    assert "SENTINEL-VISIBLE" in capfd.readouterr().err
    assert ledger.stderr_bytes_scanned >= len("SENTINEL-VISIBLE\n")


def test_ordinary_stderr_text_is_not_recorded_as_a_warning():
    """NEGATIVE CONTROL for the recovery above.

    The stream carries progress bars, tracebacks and log lines. A recogniser that
    accepted any of those would fill the certificate with noise, and a certificate full
    of noise is read by nobody — which is how a real warning gets missed.
    """
    ledger = WarningLedger()
    with recovering_worker_stderr(ledger):
        subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys\n"
                "sys.stderr.write('Ingesting traces: 100%|####| 1/1 [00:00<00:00]\\r')\n"
                "sys.stderr.write('Ingestion grid is sparse. Sparsity ratio: 3.00\\n')\n"
                "sys.stderr.write('Traceback (most recent call last):\\n')\n"
                "sys.stderr.write('some/file.py:12: not a warning line\\n')\n",
            ],
            check=True,
        )

    assert ledger.stderr_bytes_scanned > 0
    assert ledger.stderr_recovered == []


def test_a_warning_glued_to_a_progress_bar_frame_is_still_found():
    r"""``tqdm`` ends its frames with ``\r``, not ``\n``.

    Splitting on newlines alone would leave the next warning welded to the tail of a
    progress bar and unrecognisable. Measured on a real ingest, where exactly this
    interleaving occurs.
    """
    ledger = WarningLedger()
    with recovering_worker_stderr(ledger):
        subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys\n"
                "sys.stderr.write('Ingesting: 50%|##  | 1/2\\r')\n"
                "sys.stderr.write('w.py:7: UserWarning: welded to the bar\\n')\n",
            ],
            check=True,
        )

    assert [r.message for r in ledger.stderr_recovered] == ["welded to the bar"]


def test_recovery_is_reported_in_its_own_channel_never_merged():
    """Three mechanisms, three lists. Merging would misreport which one was involved.

    ``observed`` is an object the warnings machinery handed over; ``logged`` is a
    ``LogRecord``; ``stderr_recovered`` is four fields parsed out of a printed line. Only
    the first is suppressible by a filter, and only the first two carry a category the
    emitter actually raised.
    """
    ledger = WarningLedger()
    with recovering_worker_stderr(ledger), recording_warnings(ledger, reemit=False):
        warnings.warn("in this process", UserWarning, stacklevel=1)
        subprocess.run(
            [
                sys.executable,
                "-c",
                "import warnings; warnings.warn('in another', UserWarning, stacklevel=1)",
            ],
            check=True,
        )

    payload = ledger.to_json()
    assert [w["message"] for w in payload["observed"]] == ["in this process"]
    assert [r["message"] for r in payload["stderr_recovered"]] == ["in another"]
    assert payload["stderr_recovered_count"] == 1
    assert payload["stderr_recovered"][0]["channel"] == "stderr-text"


def test_the_parent_s_own_warning_is_not_double_counted():
    """The attribution claim, tested rather than asserted in prose.

    ``recording_warnings`` records instead of emitting, so a parent warning never
    reaches the descriptor and cannot appear in both lists. That is the entire basis for
    ``scope.worker_stderr_attribution``; if it stopped holding, every recovered line
    would become ambiguous.
    """
    ledger = WarningLedger()
    with recovering_worker_stderr(ledger), recording_warnings(ledger, reemit=False):
        warnings.warn("parent only", UserWarning, stacklevel=1)

    assert [w.message for w in ledger.observed] == ["parent only"]
    assert ledger.stderr_recovered == []


def test_descriptor_two_is_restored_even_when_the_block_raises():
    """This module must not leak global state, which is what it criticises upstream for.

    A leaked descriptor here is worse than a leaked warnings filter: every later write to
    stderr in the process would go into a pipe nobody drains.
    """
    import os

    before = os.fstat(2)
    with pytest.raises(RuntimeError, match="from inside the block"):
        with recovering_worker_stderr():
            raise RuntimeError("from inside the block")

    after = os.fstat(2)
    assert (after.st_dev, after.st_ino) == (before.st_dev, before.st_ino)


def test_recovery_is_bounded_on_untrusted_text():
    """Spec 3.6. Warning text can embed content from a file SDIP did not create.

    An unbounded recogniser would let a hostile source grow the certificate without
    limit. The ceiling is declared on the certificate rather than silently applied.
    """
    ledger = WarningLedger()
    with recovering_worker_stderr(ledger):
        subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys\n"
                f"for i in range({MAX_STDERR_RECORDS + 50}):\n"
                "    sys.stderr.write(f'f.py:{i}: UserWarning: flood\\n')\n",
            ],
            check=True,
        )

    assert len(ledger.stderr_recovered) == MAX_STDERR_RECORDS
    assert ledger.stderr_recovery_truncated is True
    assert ledger.to_json()["scope"]["worker_stderr_recovery_truncated"] is True


@pytest.mark.parametrize(
    "line",
    [
        "/a/b.py:303: RuntimeWarning: overflow encountered in ibm2ieee",
        "/a/b.py:1: Warning: the bare base category",
        "C:\\a\\b.py:9: UserWarning: a windows path",
    ],
)
def test_the_recogniser_accepts_the_default_warning_format(line):
    """The shape ``warnings.formatwarning`` prints, including the bare ``Warning``."""
    assert WARNING_TEXT_LINE.match(line) is not None


@pytest.mark.parametrize(
    "line",
    [
        "Traceback (most recent call last):",
        "Ingestion grid is sparse. Sparsity ratio: 3.00",
        "/a/b.py:12: not a warning at all",
        "/a/b.py:12: RuntimeError: an exception is not a warning",
    ],
)
def test_the_recogniser_rejects_everything_else(line):
    """NEGATIVE CONTROL. Each of these appears on stderr during a real ingest."""
    assert WARNING_TEXT_LINE.match(line) is None
