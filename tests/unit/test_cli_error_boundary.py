"""D60: nothing escapes the CLI as a traceback; SDIP defects are never blamed on upstream.

**Maintainer ruling (DECISIONS.md D-0088).** `main()` translated `SdipError` only, so every
upstream exception reached the operator as a traceback — measured on a foreign store handed
the wrong declaration (`NonSpecFieldError`). The boundary now classifies by **where the
exception was raised**, not by its type: walking the traceback from the deepest frame, the
first frame owned by `segy`, `mdio` or `sdip` decides. A blanket `except ValueError` would have
relabelled SDIP's own bugs as upstream refusals.

* raised inside `segy` or `mdio` → a typed upstream refusal naming the exception, the package
  and the line, exit 1 — the same code as SDIP's other refusals;
* raised anywhere else → an internal error: "a defect in SDIP, not a verdict about your data",
  exit 3, with the traceback shown only under `--debug`.
"""

from __future__ import annotations

import importlib
from typing import NoReturn

import pytest

from sdip.cli.main import EXIT_FAIL, EXIT_INTERNAL, cli
from sdip.cli.main import main as cli_entry


def _upstream_key_error() -> NoReturn:
    """A REAL upstream raise: MDIO's registry refusing an unknown template."""
    from mdio.builder.template_registry import get_template

    get_template("NoSuchTemplate")
    raise AssertionError("unreachable")  # pragma: no cover


def _sdip_defect() -> NoReturn:
    raise RuntimeError("an invariant SDIP itself broke")


def _run(monkeypatch, capsys, raiser, argv=("sdip", "verify")) -> tuple[int, str]:
    monkeypatch.setattr(cli, "main", lambda *a, **k: raiser())
    monkeypatch.setattr("sys.argv", list(argv))
    with pytest.raises(SystemExit) as caught:
        cli_entry()
    return int(caught.value.code), capsys.readouterr().err


def test_an_upstream_exception_is_a_typed_refusal_not_a_traceback(monkeypatch, capsys):
    code, err = _run(monkeypatch, capsys, _upstream_key_error)
    assert code == EXIT_FAIL
    assert "Traceback" not in err
    assert "UpstreamRefusal" in err
    assert "KeyError" in err
    assert "mdio" in err
    assert "NoSuchTemplate" in err


def test_an_sdip_defect_is_an_internal_error_never_blamed_on_upstream(monkeypatch, capsys):
    code, err = _run(monkeypatch, capsys, _sdip_defect)
    assert code == EXIT_INTERNAL
    assert "Traceback" not in err
    assert "UpstreamRefusal" not in err
    assert "not a verdict about your data" in err
    assert "--debug" in err


def test_the_debug_flag_is_parsed_by_the_real_group(monkeypatch):
    from click.testing import CliRunner

    main_module = importlib.import_module(
        "sdip.cli.main"
    )  # the package exports a same-named function

    monkeypatch.setattr(main_module, "_DEBUG", False)
    result = CliRunner().invoke(cli, ["--debug", "spec", "build", "--json"])
    assert result.exit_code == 0, result.output
    assert main_module._DEBUG is True


def test_debug_shows_the_traceback_for_an_internal_error(monkeypatch, capsys):
    main_module = importlib.import_module(
        "sdip.cli.main"
    )  # the package exports a same-named function

    monkeypatch.setattr(main_module, "_DEBUG", True)
    code, err = _run(monkeypatch, capsys, _sdip_defect)
    assert code == EXIT_INTERNAL
    assert "Traceback" in err
    assert "an invariant SDIP itself broke" in err


def test_a_spec_field_refusal_says_the_declaration_may_be_wrong(monkeypatch, capsys):
    """D60's measured case: segy refusing a field the declared spec does not define."""
    from segy.alias.core import validate_key

    def from_segy() -> NoReturn:
        validate_key("inline", "inline", ("cdp_x",))
        raise AssertionError("unreachable")  # pragma: no cover

    code, err = _run(monkeypatch, capsys, from_segy)
    assert code == EXIT_FAIL
    assert "NonSpecFieldError" in err
    assert "--override" in err
