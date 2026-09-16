"""Barred environment variables. Spec section 9.1, as amended by DECISIONS.md D-0087.

The list is every environment variable the pinned upstream reads that can change how a
source is read, what a store contains, or what upstream accepts - see
``sdip._pins.UPSTREAM_SETTINGS`` for each one and why. Until D-0087 two were barred, and
one of the ten that were not produced a measured false PASS from ``sdip verify``.

**Matching follows upstream's own case sensitivity.** ``segy``'s settings are
case-insensitive: ``segy_override_binary_header`` in lower case takes effect, so an
exact-name check would be a bypass. MDIO's are case-sensitive, so matching a lower-case
MDIO name would refuse an environment upstream never reads.

SDIP never *sets* a barred variable. A CI job parses the source tree for assignments.
"""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass
from pathlib import Path

from sdip._pins import BAR, BARRED_ENV_VARS, RECORDED_ENV_VARS, UPSTREAM_SETTINGS, UpstreamSetting

_BY_ENV: dict[str, UpstreamSetting] = {s.env: s for s in UPSTREAM_SETTINGS}


def setting_for(key: str) -> UpstreamSetting | None:
    """The upstream setting an environment key reaches, honouring its case sensitivity."""
    exact = _BY_ENV.get(key)
    if exact is not None:
        return exact
    for setting in UPSTREAM_SETTINGS:
        if not setting.case_sensitive and key.upper() == setting.env.upper():
            return setting
    return None


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
    found: dict[str, EnvFinding] = {}
    for key in env:
        setting = setting_for(key)
        if setting is not None and setting.action == BAR and setting.env not in found:
            found[setting.env] = EnvFinding(
                name=setting.env, reason=setting.reason, value_present=True
            )
    return [found[name] for name in BARRED_ENV_VARS if name in found]


def refuse_barred_env_vars(action: str, environ: dict[str, str] | None = None) -> None:
    """Raise if any barred variable is set. Called before a command reads a single byte.

    Raises:
        BarredEnvironmentError: Naming every variable found and why each is barred.
    """
    from sdip.errors import BarredEnvironmentError

    findings = check_barred_env_vars(environ)
    if findings:
        detail = "; ".join(f"{f.name}: {f.reason}" for f in findings)
        msg = f"refusing to {action}: barred environment variable set (spec 9.1). {detail}"
        raise BarredEnvironmentError(msg)


def recorded_env_vars(environ: dict[str, str] | None = None) -> dict[str, str]:
    """Set variables SDIP records rather than bars (worker counts, spec 3.4)."""
    env = os.environ if environ is None else environ
    recorded: dict[str, str] = {}
    for key, value in env.items():
        setting = setting_for(key)
        if setting is not None and setting.env in RECORDED_ENV_VARS:
            recorded[setting.env] = value
    return dict(sorted(recorded.items()))


def scrub_barred_env_vars(environ: dict[str, str] | None = None) -> list[str]:
    """Remove barred variables from ``environ`` and return the names removed.

    For use only when constructing a child-process environment that SDIP controls.
    It is never used to paper over the operator's own shell: ``sdip doctor`` reports
    the parent environment as it found it.
    """
    env = os.environ if environ is None else environ
    removed = [
        key
        for key in list(env)
        if (setting := setting_for(key)) is not None and setting.action == BAR
    ]
    for key in removed:
        del env[key]
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
                and _barred(target.slice.value)
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
            if isinstance(argument, ast.Constant) and _barred(argument.value):
                return str(argument.value)
            if isinstance(argument, ast.Dict):
                for key in argument.keys:
                    if isinstance(key, ast.Constant) and _barred(key.value):
                        return str(key.value)
    return None


def _barred(value: object) -> bool:
    """True when a literal names a barred variable, in any spelling upstream honours."""
    if not isinstance(value, str):
        return False
    setting = setting_for(value)
    return setting is not None and setting.action == BAR


def _is_environ(node: ast.AST) -> bool:
    """True when ``node`` refers to the process environment mapping."""
    if isinstance(node, ast.Attribute):
        return node.attr == "environ"
    return isinstance(node, ast.Name) and node.id == "environ"
