"""OPEN_DEBTS D13, DECISIONS.md D-0106 - every `§N` a public file cites resolves in public.

The specification and the operating contract are kept off the published repository, so a
reader cannot follow a `§4.2` to its source. `CITATIONS.md` names, for every section number
cited anywhere public, a public file and a verbatim line that restates the rule. This test
holds the index to the tree: a citation with no entry fails, and so does an entry whose line
no longer exists, appears twice, or sits in a file that is not published.

It cannot tell whether a restatement says what the private text says - that stays a
maintainer's reading. It makes drift visible: a new citation, or an edited restatement,
fails here instead of going stale silently.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

from sdip.cli.doctor import NEVER_PUBLISH

INDEX = "CITATIONS.md"
SELF = "tests/unit/test_section_citations.py"  # its controls cite sections that do not exist
CITE = re.compile(r"§\s?(\d+(?:\.\d+)*)")
SCHEMES = {"spec", "contract", "external"}


def public_files(root: Path) -> dict[str, str]:
    """Every tracked, published text file, path -> text. The index and this file excluded."""
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=root, capture_output=True, text=True, check=True
    ).stdout.split("\n")
    files: dict[str, str] = {}
    for name in filter(None, tracked):
        firewalled = any(name == p or name.startswith(f"{p}/") for p in NEVER_PUBLISH)
        if name in (INDEX, SELF) or firewalled:
            continue
        try:
            files[name] = (root / name).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
    return files


def load_index(text: str) -> list[dict[str, str]]:
    match = re.search(r"```json\n(.*?)\n```", text, re.DOTALL)
    assert match, f"{INDEX} carries no ```json block"
    return json.loads(match.group(1))


def problems(files: dict[str, str], entries: list[dict[str, str]]) -> list[str]:
    found: list[str] = []
    cited = {n for text in files.values() for n in CITE.findall(text)}
    indexed = {e["section"] for e in entries}
    found += [f"§{n} is cited but has no entry in {INDEX}" for n in sorted(cited - indexed)]
    for e in entries:
        where = f"§{e['section']} ({e['scheme']}) -> {e['file']}"
        if e["scheme"] not in SCHEMES:
            found.append(f"{where}: scheme must be one of {sorted(SCHEMES)}")
        if e["file"] not in files:
            found.append(f"{where}: not a tracked, published file")
            continue
        count = files[e["file"]].count(e["anchor"])
        if count != 1:
            found.append(f"{where}: anchor found {count} times, must be exactly once")
    return found


def test_every_cited_section_resolves_to_a_public_restatement(repo_root):
    entries = load_index((repo_root / INDEX).read_text(encoding="utf-8"))
    assert problems(public_files(repo_root), entries) == []


# --- negative controls: each must produce exactly its problem (SP11) ----------------------

GOOD = {"README.md": "Rules: we never use a tolerance anywhere.\nSee §4.2.\n"}
ENTRY = {"section": "4.2", "scheme": "spec", "file": "README.md", "anchor": "never use a tolerance"}


def test_the_control_baseline_has_no_problems():
    assert problems(GOOD, [ENTRY]) == []


@pytest.mark.parametrize(
    ("files", "entries", "expected"),
    [
        (GOOD | {"x.py": "# see §99.9\n"}, [ENTRY], "§99.9 is cited but has no entry"),
        (GOOD, [ENTRY | {"anchor": "a line that is not there"}], "anchor found 0 times"),
        (
            {"README.md": GOOD["README.md"] * 2},
            [ENTRY],
            "anchor found 2 times",
        ),
        (GOOD, [ENTRY | {"file": "docs/spec.md"}], "not a tracked, published file"),
        (GOOD, [ENTRY | {"scheme": "rumour"}], "scheme must be one of"),
    ],
)
def test_each_corruption_is_caught(files, entries, expected):
    found = problems(files, entries)
    assert len(found) == 1, found
    assert expected in found[0]


def test_firewalled_files_are_never_counted_as_public(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "s.md").write_text("§1\n")
    (tmp_path / "README.md").write_text("§2\n")
    subprocess.run(["git", "add", "-f", "-A"], cwd=tmp_path, check=True)
    assert set(public_files(tmp_path)) == {"README.md"}
