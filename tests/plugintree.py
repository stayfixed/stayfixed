"""The builders of a source repository holding the plugin's nine paths, for the tests reading one.

`scripts/plugin_tree.py`'s own tests, the payload walk (`tests/test_payload.py`) and the release
check's tag tests (`tests/scripts/test_release.py`) each built such a repository with a copy of
these, and the copies had drifted: three spellings of the nine paths, two of the files under them,
and a payload test importing its builder from another test module. Here once, as
`tests/gitfixture.py` is for the `git` they run.

The nine paths and the files under them are spelled out here and never read from the script's
`PLUGIN_PATHS`: an expectation read from the subject is the subject compared with itself. Every
`git` goes through `tests.gitfixture.git`, the sealed runner, so the developer's configuration
never shapes a fixture; a test that means the owner's configuration writes it into the test
`HOME`'s `.gitconfig`, which only the code under test reads.
"""

from __future__ import annotations

from pathlib import Path

from tests.gitfixture import git

# The nine paths the runtime reads, as the plugin's tree must hold them.
NINE = (
    ".claude-plugin/plugin.json",
    ".codex-plugin/plugin.json",
    "hooks",
    "scripts/stayfixed",
    "src/stayfixed",
    "skills",
    "agents",
    "README.md",
    "LICENSE",
)
# One file under each of the nine, with its git mode: the wrapper and the launcher are executable,
# and both manifests name the version a plugin commit's message carries.
PLUGIN_FILES: dict[str, tuple[bytes, str]] = {
    ".claude-plugin/plugin.json": (b'{"name": "stayfixed", "version": "1.2.3"}\n', "100644"),
    ".codex-plugin/plugin.json": (b'{"name": "stayfixed", "version": "1.2.3"}\n', "100644"),
    "hooks/hooks.json": (b"{}\n", "100644"),
    "hooks/run-hook.sh": (b"#!/bin/sh\nexit 0\n", "100755"),
    "scripts/stayfixed": (b"#!/usr/bin/env python3\n", "100755"),
    "src/stayfixed/__init__.py": (b'__version__ = "1.2.3"\n', "100644"),
    "skills/close-bug/SKILL.md": (b"# close a bug\n", "100644"),
    "agents/navigator.md": (b"# navigator\n", "100644"),
    "README.md": (b"# stayfixed\n", "100644"),
    "LICENSE": (b"MIT\n", "100644"),
}


def write(root: Path, files: dict[str, tuple[bytes, str]]) -> None:
    """Each file of `files` under `root`: its bytes, and the permissions its git mode names."""
    for path, (content, mode) in files.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        target.chmod(0o755 if mode == "100755" else 0o644)


def commit(root: Path, message: str = "a commit") -> str:
    """Everything under `root` committed, and the commit's id."""
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", message)
    return git(root, "rev-parse", "HEAD").strip()


def plugin_source(tmp_path: Path, files: dict[str, tuple[bytes, str]] | None = None) -> Path:
    """An initialised repository at `tmp_path / "source"` whose one commit holds `files`, or
    `PLUGIN_FILES` when none are given."""
    root = tmp_path / "source"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    write(root, files or PLUGIN_FILES)
    commit(root)
    return root
