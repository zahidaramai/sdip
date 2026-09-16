"""Every command that reads a source or a store takes the same survey declaration.

**Why this is structural rather than a list of cases (D47, DECISIONS.md D-0087).** Commit
``8e13c10`` added ``--override`` to two of the five commands that read a source or a
store. Nothing failed, because nothing asserted the commands agree — each test exercised
the one command it was written for. This test does not enumerate options per command; it
asserts the commands are *identical* in the declaration they accept, so the next input
added to one command and not the others fails here on the day it is written.
"""

from __future__ import annotations

from pathlib import Path

import click
import pytest

from sdip.cli.main import cli

DECLARATION_OPTIONS = ("--revision", "--template", "--override")
STORE_COMMANDS = ("ingest", "verify", "export", "certify")


def _options(command: click.Command) -> dict[str, click.Option]:
    return {
        opt: param
        for param in command.params
        if isinstance(param, click.Option)
        for opt in param.opts
    }


@pytest.mark.parametrize("name", STORE_COMMANDS)
def test_every_store_command_takes_the_whole_declaration(name):
    options = _options(cli.commands[name])
    missing = [opt for opt in DECLARATION_OPTIONS if opt not in options]
    assert missing == [], f"sdip {name} cannot be handed: {missing}"


@pytest.mark.parametrize("option", DECLARATION_OPTIONS)
def test_the_declaration_options_are_the_same_option_everywhere(option):
    """Same type, same choices, same default. A differing default IS the D47 defect."""
    seen = {}
    for name in STORE_COMMANDS:
        param = _options(cli.commands[name])[option]
        choices = tuple(param.type.choices) if isinstance(param.type, click.Choice) else None
        seen[name] = (param.name, choices, param.default, param.required)
    assert len(set(seen.values())) == 1, seen


def test_spec_build_takes_the_part_of_the_declaration_a_spec_depends_on():
    options = _options(cli.commands["spec"].commands["build"])
    assert "--revision" in options
    assert "--override" in options


def test_override_help_says_it_relaxes_nothing():
    """The option's help must say plainly what ``--override`` is and what it is not.

    ``certify``'s own refusal said "there is no override", meaning no way to skip the
    clean-tree bar. An option called ``--override`` on that command reads as the opposite
    unless its help says so.
    """
    for name in STORE_COMMANDS:
        help_text = " ".join((_options(cli.commands[name])["--override"].help or "").split())
        assert "relaxes no gate" in help_text, name


def test_no_refusal_uses_the_flag_name_to_mean_a_bypass():
    """Every refusal that said "There is no override" now contradicts a real option."""
    import sdip

    root = Path(sdip.__file__).parent
    offenders = [
        str(path.relative_to(root))
        for path in sorted(root.rglob("*.py"))
        if "There is no override" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []
