"""Provenance: hashing, environment capture, git state (spec 11.3)."""

from __future__ import annotations

import hashlib
import subprocess

from sdip.provenance import (
    capture_environment,
    capture_git_state,
    sha256_file,
    sha256_tree,
)


def test_sha256_file_matches_hashlib(tmp_path):
    payload = b"\x00\x01\x02SEG-Y-ish\xff" * 1000
    path = tmp_path / "f.bin"
    path.write_bytes(payload)
    assert sha256_file(path) == hashlib.sha256(payload).hexdigest()


def test_sha256_file_is_streamed_and_chunk_size_independent(tmp_path):
    payload = bytes(range(256)) * 500
    path = tmp_path / "f.bin"
    path.write_bytes(payload)
    expected = hashlib.sha256(payload).hexdigest()
    assert sha256_file(path, chunk_size=7) == expected
    assert sha256_file(path, chunk_size=1 << 20) == expected


def test_sha256_file_detects_a_single_flipped_bit(tmp_path):
    """NEGATIVE CONTROL. This is the primitive the whole project rests on."""
    payload = bytearray(b"A" * 4096)
    a = tmp_path / "a.bin"
    a.write_bytes(payload)
    payload[2048] ^= 0x01
    b = tmp_path / "b.bin"
    b.write_bytes(payload)
    assert sha256_file(a) != sha256_file(b)


def test_empty_file_hashes_to_the_known_empty_digest(tmp_path):
    path = tmp_path / "empty.bin"
    path.write_bytes(b"")
    assert sha256_file(path) == ("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")


def test_sha256_tree_is_deterministic_and_sorted(tmp_path):
    for name in ("c.txt", "a.txt", "b/d.txt"):
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(name)
    first = sha256_tree(tmp_path)
    second = sha256_tree(tmp_path)
    assert first == second
    assert list(first) == sorted(first)
    assert list(first) == ["a.txt", "b/d.txt", "c.txt"]


def test_sha256_tree_honours_exclude(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    (tmp_path / "keep.txt").write_text("keep")
    assert list(sha256_tree(tmp_path, exclude=(".git",))) == ["keep.txt"]


def test_capture_environment_records_the_pins():
    env = capture_environment().to_json()
    assert env["packages"]["multidimio"] == "1.2.1"
    assert env["packages"]["segy"] == "0.6.0"
    assert env["python"].startswith("3.12") or env["python"].startswith("3.13")
    pins = env["declared_pins"]
    assert set(pins) == {"multidimio", "segy"}


def test_capture_environment_labels_sha_verification_honestly():
    """SP8 / open debt D9. Never claim a verification that did not happen."""
    for record in capture_environment().to_json()["declared_pins"].values():
        assert record["sha_verification"] == "declared-not-runtime-verified"


def test_clean_repository_is_certifiable(git_repo):
    state = capture_git_state(git_repo)
    assert state.is_repository
    assert state.dirty is False
    assert state.dirty_paths == ()
    assert state.commit and len(state.commit) == 40
    assert state.certifiable


def test_modified_file_makes_the_tree_dirty(git_repo):
    """NEGATIVE CONTROL: a modification must block certification."""
    (git_repo / "a.txt").write_text("changed\n")
    state = capture_git_state(git_repo)
    assert state.dirty
    assert "a.txt" in state.dirty_paths
    assert not state.certifiable


def test_untracked_file_makes_the_tree_dirty(git_repo):
    """NEGATIVE CONTROL.

    An untracked file can change a run's behaviour just as easily as a modified one,
    and neither is in the committed record.
    """
    (git_repo / "sneaky.py").write_text("import os\n")
    state = capture_git_state(git_repo)
    assert state.dirty
    assert "sneaky.py" in state.dirty_paths
    assert not state.certifiable


def test_staged_but_uncommitted_change_is_dirty(git_repo):
    (git_repo / "a.txt").write_text("staged\n")
    subprocess.run(["git", "add", "-A"], cwd=git_repo, check=True)
    assert capture_git_state(git_repo).dirty


def test_non_repository_is_never_certifiable(tmp_path):
    state = capture_git_state(tmp_path)
    assert state.is_repository is False
    assert state.certifiable is False
    assert state.dirty is True
