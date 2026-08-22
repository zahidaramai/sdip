"""Barred environment variables. Spec section 9.1.

``MDIO_IGNORE_CHECKS`` demotes MDIO's grid-sparsity error to a log line - a
suppressible gate is not a gate (SP11). ``MDIO__IMPORT__RAW_HEADERS`` is deprecated
upstream and SDIP reaches full header persistence through the public API instead
(spec 3.2), so depending on it is a specification violation.

SDIP never *sets* either variable. A CI job greps the source tree for assignments.
"""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass
from pathlib import Path

from sdip._pins import BARRED_ENV_VARS


@dataclass(frozen=True, slots=True)
class EnvFinding:
    """One barred variable found set in the process environment."""

    name: str
    reason: str
    value_present: bool


def check_barred_env_vars(environ: dict[str, str] | None = None) -> list[EnvFinding]:
    """Return a finding for every barred variable present in ``environ``.

    Presence alone is the failure. A barred variable set to ``"0"`` or the empty
    string still fails: SDIP does not model upstream's truthiness rules, and a
    variable that is set at all is a signal the operator intended to change
    behaviour.

    Args:
        environ: Mapping to inspect. Defaults to ``os.environ``.

    Returns:
        Findings in declaration order. An empty list means the environment is clean.
    """
    env = os.environ if environ is None else environ
    return [
        EnvFinding(name=name, reason=reason, value_present=name in env)
        for name, reason in BARRED_ENV_VARS.items()
        if name in env
    ]


def scrub_barred_env_vars(environ: dict[str, str] | None = None) -> list[str]:
    """Remove barred variables from ``environ`` and return the names removed.

    For use only when constructing a child-process environment that SDIP controls.
    It is never used to paper over the operator's own shell: ``sdip doctor`` reports
    the parent environment as it found it.
    """
    env = os.environ if environ is None else environ
    removed = [name for name in BARRED_ENV_VARS if name in env]
    for name in removed:
        del env[name]
    return removed


def scan_source_for_barred_assignments(root: Path) -> list[str]:
    """Return every place in ``root`` that *assigns* a barred environment variable.

    Parsed with ``ast``, not grepped. A grep for the variable names flags this
    module's own docstring, the CI workflow that checks for them, and every piece of
    documentation that explains why they are barred - and a gate that fires on prose
    is a gate that gets switched off (the same lesson as ``DECISIONS.md`` D-0005).

    Detected forms::

        os.environ["MDIO_IGNORE_CHECKS"] = "1"
        os.environ.setdefault("MDIO_IGNORE_CHECKS", "1")
        os.putenv("MDIO_IGNORE_CHECKS", "1")
        monkeypatch.setenv("MDIO_IGNORE_CHECKS", "1")

    Args:
        root: Directory to walk. Every ``*.py`` beneath it is parsed.

    Returns:
        ``"<path>:<line>: <detail>"`` per finding, sorted. Empty means clean.
    """
    findings: list[str] = []
    for path in sorted(root.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:  # pragma: no cover - a file that cannot parse is a lint job
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign | ast.Call):
                continue
            name = _assigned_barred_name(node)
            if name is not None:
                findings.append(f"{path}:{node.lineno}: assigns {name}")
    return findings


def _assigned_barred_name(node: ast.Assign | ast.Call) -> str | None:
    """Return the barred variable this node assigns, or None."""
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if (
                isinstance(target, ast.Subscript)
                and isinstance(target.slice, ast.Constant)
                and target.slice.value in BARRED_ENV_VARS
                and _is_environ(target.value)
            ):
                return str(target.slice.value)
        return None

    if isinstance(node, ast.Call):
        func = node.func
        attribute = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if attribute not in {"setdefault", "setenv", "putenv", "update"}:
            return None
        for argument in node.args:
            if isinstance(argument, ast.Constant) and argument.value in BARRED_ENV_VARS:
                return str(argument.value)
            if isinstance(argument, ast.Dict):
                for key in argument.keys:
                    if isinstance(key, ast.Constant) and key.value in BARRED_ENV_VARS:
                        return str(key.value)
    return None


def _is_environ(node: ast.AST) -> bool:
    """True when ``node`` refers to the process environment mapping."""
    if isinstance(node, ast.Attribute):
        return node.attr == "environ"
    return isinstance(node, ast.Name) and node.id == "environ"
