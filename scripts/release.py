#!/usr/bin/env python3
"""This repository's own release discipline: one version everywhere, the changelog, the record.

    uv run python scripts/release.py check [--tag TAG]            # one version everywhere
    uv run python scripts/release.py notes --version X.Y.Z [--draft]  # assemble CHANGELOG.md
    uv run python scripts/release.py hashes [--check]              # the shipped files' record

These three commands only ever checked the stayfixed repository itself, so they live beside it
rather than in the installed CLI. What shipped code does read stays in `stayfixed.release`: the
record's reader (`doctor files` compares an installed plugin against it) and the tag a version
is released under (`init` pins it). `RELEASING.md` is the process these commands serve.

The commands go through the CLI frame's `run`, so they keep its contract: `--json` anywhere on
the line, exit `0`, `1` for findings and `2` for a refusal or an internal error.

**Findings are returned, not raised.** These commands once reported a finding by raising
`Failure`, and the cost was in `--json`: the frame turns a `Failure` into
`{"error": "failed", "summary": "failed: ..."}` and drops `Result.data` entirely, so the
machine-readable object changed *shape* between a clean run and a drifted one -- a consumer that
read `versions` on success had nothing to read on the run it actually cared about. `Failure` is
still raised for what it is for: a source this gate cannot parse at all (`MalformedSource`) and
a towncrier that cannot be run.

**`notes --draft` prints more than one line**, and it is deliberate: every stayfixed command
gets one summary line because a line is what a caller reads, and a draft's whole purpose is that
a person reads the section towncrier *would* write before it is written. Under `--json` it keeps
the one-line contract.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path, PurePosixPath
from typing import Any

from stayfixed import fsops
from stayfixed.cli import JSON_EPILOG, run
from stayfixed.command import CHECK_HELP, ROOT_HELP
from stayfixed.config.loader import UNPARSEABLE
from stayfixed.errors import Failure, Refusal
from stayfixed.gitenv import git_run
from stayfixed.printed import quoted
from stayfixed.release.api import (
    FORMAT,
    HASHED_FILES,
    PACKAGE,
    RECORD,
    digests,
    read_record,
    tag_for,
)
from stayfixed.result import Result
from stayfixed.runner import NOT_FOUND, Runner, subprocess_runner

# How a message tells the reader to run one of these commands again.
COMMAND = "uv run python scripts/release.py"

PYPROJECT = "pyproject.toml"
LOCKFILE = "uv.lock"
SOURCES = (
    PYPROJECT,
    LOCKFILE,
    "src/stayfixed/__init__.py",
    ".claude-plugin/plugin.json",
    ".codex-plugin/plugin.json",
    "CHANGELOG.md",
)
MARKETPLACE = ".claude-plugin/marketplace.json"
# The most files a plugin folder holds without the Claude plugin directory holding the listing for
# a reviewer: "Keep the plugin to 512 files or fewer", its pre-submission checklist says
# (https://claude.com/docs/plugins/pre-submission-checklist, read 2026-10-05). The number is the
# page's and no file's here; `tests/test_payload.py` reads it as its `FILES_MAX`.
PLUGIN_FILES_MAX = 512
START = "<!-- towncrier release notes start -->"
_INIT = re.compile(r'^__version__\s*=\s*"([^"]+)"', re.MULTILINE)
_HEADING = re.compile(r"^## (\S+)", re.MULTILINE)

TAG_HELP = (
    "the tag this run was created from; the six sources and the changelog must agree with it, "
    "and the plugin folder must hold no more files than the plugin directory lists unheld"
)


# --- One version string everywhere --------------------------------------------------------------


class MalformedSource(Failure):
    """A version source that exists but cannot be parsed; the message names which one."""


def _object(name: str, text: str) -> dict[str, Any]:
    """A JSON source's top level, which is read with `.get` and so must be an object."""
    document = json.loads(text)
    if not isinstance(document, dict):
        raise MalformedSource(f"{name} is valid JSON but its top level is not an object")
    return document


def _parse(name: str, text: str) -> str | None:
    # Valid TOML or JSON of the wrong shape decodes cleanly, so `_read`'s decoder catches never
    # see it: a `.get` on a list or a string raises AttributeError, which reaches the caller as
    # an unlabelled internal error naming no file. Each shape a source is read in is asked first.
    if name == PYPROJECT:
        project = tomllib.loads(text).get("project", {})
        if not isinstance(project, dict):
            raise MalformedSource(f"{name} is valid TOML but its project is not a table")
        version = project.get("version")
        return str(version) if version is not None else None
    if name == LOCKFILE:
        # `uv sync --locked` fails the install step on a stale lockfile with a
        # dependency-shaped message, before this gate — built to catch exactly this — can speak.
        packages = tomllib.loads(text).get("package", [])
        if not isinstance(packages, list) or not all(isinstance(e, dict) for e in packages):
            raise MalformedSource(f"{name} is valid TOML but its package is not a list of tables")
        for entry in packages:
            if entry.get("name") == PACKAGE:
                version = entry.get("version")
                return str(version) if version is not None else None
        return None
    if name.endswith("__init__.py"):
        match = _INIT.search(text)
        return match.group(1) if match else None
    if name.endswith(".json"):
        version = _object(name, text).get("version")
        return str(version) if version is not None else None
    released = text.split(START, 1)[1] if START in text else text
    match = _HEADING.search(released)
    return match.group(1) if match else None


def _read(root: Path, name: str) -> str | None:
    path = root / name
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise MalformedSource(f"{name} is not UTF-8 text") from None
    # `json` answers nesting past its depth with `RecursionError` too, so the arm that catches it
    # names the language by the source: a deep `plugin.json` was reported as "not valid TOML".
    language = "JSON" if name.endswith(".json") else "TOML"
    try:
        return _parse(name, text)
    except (json.JSONDecodeError, *UNPARSEABLE) as exc:
        raise MalformedSource(f"{name} is not valid {language}: {exc}") from None


def collect(root: Path) -> dict[str, str | None]:
    return {name: _read(root, name) for name in SOURCES}


def fragment_types(root: Path) -> frozenset[str]:
    """The types `[[tool.towncrier.type]]` declares, read rather than hardcoded here.

    A predicate that spelled the types out would drift from the configuration towncrier
    itself reads, and the drift would show up as a release gate that is wrong in silence.
    """
    tool = _pyproject(root).get("tool", {})
    towncrier = tool.get("towncrier", {}) if isinstance(tool, dict) else {}
    declared = towncrier.get("type", []) if isinstance(towncrier, dict) else []
    return frozenset(
        str(entry["directory"])
        for entry in declared
        if isinstance(entry, dict) and "directory" in entry
    )


def _pyproject(root: Path) -> dict[str, Any]:
    path = root / PYPROJECT
    if not path.is_file():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        raise MalformedSource(f"{PYPROJECT} is not UTF-8 text") from None
    except UNPARSEABLE as exc:
        raise MalformedSource(f"{PYPROJECT} is not valid TOML: {exc}") from None


def _is_fragment(name: str, types: frozenset[str]) -> bool:
    """towncrier's own shape: `<something>.<type>.md`."""
    stem, _, extension = name.rpartition(".")
    if extension != "md" or not stem:
        return False
    prefix, _, kind = stem.rpartition(".")
    return bool(prefix) and kind in types


def fragments(root: Path) -> list[str]:
    """The real towncrier fragments `changelog.d` holds, by name, the types read once."""
    directory = root / "changelog.d"
    if not directory.is_dir():
        return []
    types = fragment_types(root)
    return sorted(entry.name for entry in directory.iterdir() if _is_fragment(entry.name, types))


def pending_fragments(root: Path) -> bool:
    """Whether `changelog.d` holds a real towncrier fragment, letting CHANGELOG.md lag.

    Asking instead "any entry not literally named .gitkeep" meant a stray `.DS_Store` — which
    Finder writes merely by opening the directory — silenced a genuine version drift and turned
    a red release gate green.
    """
    return bool(fragments(root))


def _marketplace_entries(root: Path) -> list[dict[str, Any]]:
    """The marketplace's `plugins` entries, each an object, or none when there is no file."""
    marketplace = root / MARKETPLACE
    if not marketplace.is_file():
        return []
    try:
        text = marketplace.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise MalformedSource(f"{MARKETPLACE} is not UTF-8 text") from None
    try:
        entries = _object(MARKETPLACE, text).get("plugins", [])
    except (json.JSONDecodeError, RecursionError) as exc:
        raise MalformedSource(f"{MARKETPLACE} is not valid JSON: {exc}") from None
    # A string entry was read with `in`, a substring test, and a string `plugins` as a list of
    # its characters, so the rule passed over both in silence.
    if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):
        raise MalformedSource(
            f"{MARKETPLACE} is valid JSON but its plugins is not a list of objects"
        )
    return entries


def check(root: Path, *, tag: str | None = None) -> list[str]:
    """What stops this tree from being released as one version, at `tag` when one is given."""
    return checked(root, tag=tag)[0]


def checked(root: Path, *, tag: str | None = None) -> tuple[list[str], dict[str, str | None]]:
    """`check`'s problems, and the version each source carried as it read them, so a caller that
    reports both reads the tree once."""
    # Four different conditions used to share one wrong message, so a user who typoed --root,
    # or ran the command in their own project (--root defaults to "."), was told their
    # pyproject.toml lacked a version key. A path that exists but is not a directory needs its
    # own line rather than the missing-path one: `--root ./pyproject.toml` was told the file
    # does not exist, and a gate that exists to stop asserting untrue things about the user's
    # tree must not assert one itself.
    found = collect(root)
    if not root.exists():
        return [f"{root} does not exist; --root must name a repository root"], found
    if not root.is_dir():
        return [f"{root} is not a directory; --root must name a repository root"], found
    if not (root / PYPROJECT).is_file():
        return [f"{root} has no {PYPROJECT}; --root must name a repository root"], found
    canonical = found[PYPROJECT]
    if canonical is None:
        return [f"{PYPROJECT} has no [project].version"], found
    pending = fragments(root)
    problems: list[str] = []
    if tag is not None:
        if tag not in tag_for(canonical):
            # **Say what was checked, do not re-derive a version from the tag.** This used to
            # be `tag.split("v", 1)[-1]` — a split on the first `v` anywhere in the string and
            # not a parse — so `--tag 1.2.3` reported `tag 1.2.3 names 1.2.3; pyproject.toml
            # says '1.2.3'`, two identical strings asserted to disagree, and `--tag dev-v1.2.3`
            # reported `names -v1.2.3`. The membership test above is exact and was always
            # right; only the sentence was invented. Both slips are the ones `RELEASING.md`
            # invites, because a human types this flag by hand right after a tool prints
            # `stayfixed--vX.Y.Z`. The existing cases passed by accident: every tag they
            # exercised began with `v` and carried no earlier one.
            workflow_tag, platform_tag = tag_for(canonical)
            problems.append(
                f"tag {tag} is neither {workflow_tag} nor {platform_tag}; "
                f"{PYPROJECT} says {canonical!r}"
            )
        if pending:
            problems.append(
                f"changelog.d still holds {len(pending)} fragment(s); run `{COMMAND} notes "
                f"--version {canonical}` before tagging"
            )
    for name, value in found.items():
        if name == "CHANGELOG.md" and tag is None and pending:
            continue
        if value != canonical:
            problems.append(f"{name} says {value!r}; {PYPROJECT} says {canonical!r}")
    for entry in _marketplace_entries(root):
        if "version" in entry:
            problems.append(
                f"{MARKETPLACE} entry {entry.get('name')!r} carries a version; "
                "plugin.json is the only source"
            )
    # The record of the shipped files is held current here and not only at a tag, so a
    # wrapper edited without `hashes` fails the gate the same commit.
    #
    # Asked of the recorded files themselves and not of a `hooks/` directory. `--root` defaults
    # to `.`, and a run somewhere other than this repository must not be told a record it never
    # had is missing — and plenty of projects have a `hooks/` directory, which is what the first
    # spelling of this actually tested. Either the record is here, or every file it would name
    # is: the first keeps a tree whose wrapper was deleted honest, the second is how a checkout
    # with no record yet is told to write one.
    if (root / RECORD).is_file() or all((root / name).is_file() for name in HASHED_FILES):
        problems += drift(root)
    # At a tag and never on a pull request: a pull request may carry the tree past the count, and
    # a release is what the directory lists.
    if tag is not None:
        problems += plugin_folder_counts(root)
    return problems, found


def plugin_folder_counts(root: Path) -> list[str]:
    """Each plugin folder the marketplace names in this tree that holds more files than the
    plugin directory lists without holding the listing for a reviewer.

    Counted in `HEAD`'s tree, as the directory reads a commit: a file on disk or only staged is
    not in what it scans. A `source` that is not a path fetches the plugin from elsewhere, so this
    tree holds none of it. A folder git cannot list is a problem rather than nought files: the
    gate that cannot count does not pass.
    """
    problems = []
    for entry in _marketplace_entries(root):
        source = entry.get("source")
        if not isinstance(source, str):
            continue
        folder = str(PurePosixPath(source))
        code, listing = git_run(root, "ls-tree", "-r", "-z", "--name-only", "HEAD", "--", folder)
        if code != 0:
            problems.append(
                f"the plugin folder {quoted(source)} could not be counted in HEAD's tree "
                f"(git exited {code}); run the check in the git checkout the tag names"
            )
            continue
        count = listing.count("\0")
        if count > PLUGIN_FILES_MAX:
            problems.append(
                f"the plugin folder {quoted(source)} holds {count} files, over the "
                f"{PLUGIN_FILES_MAX} the plugin directory lists unheld; publish the plugin "
                "from its own repository first (RELEASING.md, section 2)"
            )
    return problems


# --- The changelog ------------------------------------------------------------------------------


def build(root: Path, *, version: str, draft: bool, runner: Runner) -> str:
    """Assemble `CHANGELOG.md` from `changelog.d/` through towncrier, or render it under `draft`.

    A wrapper and nothing more: towncrier owns the rendering, `pyproject.toml`'s
    `[tool.towncrier]` owns the format, and this function owns two refusals — the version must
    be the project's, and a missing towncrier is named as the development dependency it is.
    """
    current = collect(root)["pyproject.toml"]
    if version != current:
        raise Refusal(
            f"--version {version} is not the project's ({current!r}); set the version "
            f"everywhere first — `{COMMAND} check` names the six places — and then "
            "assemble the changelog under it"
        )
    argv = ["towncrier", "build", "--version", version, "--yes"] + (["--draft"] if draft else [])
    done = runner.launch(argv, root)
    if done.code == NOT_FOUND:
        raise Failure(
            "towncrier could not be run; it is a development dependency, and `uv sync` installs it"
        )
    if done.code != 0:
        raise Failure(f"towncrier exited {done.code}: {done.stderr.strip()}")
    return done.stdout


# --- The record of the shipped files ------------------------------------------------------------


def write_record(root: Path) -> None:
    """Record every shipped file, or refuse: a partial record is not a record of a release.

    Not because a partial record would read as clean — both readers walk `HASHED_FILES` and
    would flag the file it omits. It is refused because the alternative is a record that says
    "these are the files the release shipped" while naming two of three, so every reader of it
    afterwards is reporting drift against a claim nobody meant to make. The failure belongs at
    the moment of writing, where the tree that is missing a file can still be fixed.
    """
    found = digests(root)
    if len(found) != len(HASHED_FILES):
        missing = [name for name in HASHED_FILES if name not in found]
        raise Failure(
            f"cannot record a release without {', '.join(missing)}; the record must name "
            "every shipped file"
        )
    body = json.dumps({"format": FORMAT, "files": found}, indent=2, sort_keys=True) + "\n"
    fsops.write_within(root, RECORD, body)


def drift(root: Path) -> list[str]:
    """Every way the tree and the record disagree, in the reader's own words.

    Both directions on purpose: a file the record names and the tree lacks is drift, and so is
    one whose bytes moved. A walk over the record alone would call a deleted file a match.
    """
    recorded = read_record(root)
    if recorded is None:
        return [f"{RECORD} is missing; run `{COMMAND} hashes`"]
    actual = digests(root)
    problems = [
        f"{RECORD} names {name}, which is not in the tree"
        for name in recorded
        if name not in actual
    ]
    problems += [
        f"{RECORD} does not match {name}; run `{COMMAND} hashes`"
        for name in actual
        if recorded.get(name) != actual[name]
    ]
    return problems


# --- The commands -------------------------------------------------------------------------------


def run_check(args: argparse.Namespace) -> Result:
    root = Path(args.root)
    problems, versions = checked(root, tag=args.tag)
    data = {"problems": problems, "versions": versions}
    if problems:
        return Result("version drift: " + "; ".join(problems), data, exit_code=1)
    return Result(f"one version everywhere: {versions['pyproject.toml']}", data)


def run_notes(args: argparse.Namespace) -> Result:
    root = Path(args.root)
    rendered = build(root, version=args.version, draft=args.draft, runner=subprocess_runner())
    if args.draft:
        return Result(rendered.rstrip("\n"), {"draft": rendered})
    return Result(f"CHANGELOG.md carries {args.version}")


def run_hashes(args: argparse.Namespace) -> Result:
    root = Path(args.root)
    if args.check:
        problems = drift(root)
        data = {"problems": problems, "files": sorted(HASHED_FILES)}
        if problems:
            return Result("release record drift: " + "; ".join(problems), data, exit_code=1)
        return Result(f"{len(HASHED_FILES)} shipped file(s) match the release record", data)
    write_record(root)
    return Result(f"recorded {len(HASHED_FILES)} shipped file(s)", {"files": sorted(HASHED_FILES)})


def parser() -> argparse.ArgumentParser:
    """The script's parser. Each command's one sentence is both its line in the listing and the
    description its own `--help` opens with: argparse keeps `help=` for the parent's listing
    only, which the installed CLI's frame fills in for every command and this script does by
    hand."""
    top = argparse.ArgumentParser(
        prog="scripts/release.py",
        description="Release discipline for the stayfixed repository itself.",
        epilog=JSON_EPILOG,
    )
    sub = top.add_subparsers(dest="command", metavar="<command>")

    def command(name: str, sentence: str) -> argparse.ArgumentParser:
        return sub.add_parser(name, help=sentence, description=sentence, epilog=JSON_EPILOG)

    cmd = command("check", "every version string agrees")
    cmd.add_argument("--root", default=".", help=ROOT_HELP)
    cmd.add_argument("--tag", default=None, help=TAG_HELP)
    cmd.set_defaults(func=run_check)
    notes = command("notes", "assemble CHANGELOG.md from changelog.d through towncrier")
    notes.add_argument("--version", required=True, help="the version to assemble the section under")
    notes.add_argument("--draft", action="store_true", help="render without writing")
    notes.add_argument("--root", default=".", help=ROOT_HELP)
    notes.set_defaults(func=run_notes)
    hashes = command("hashes", "record the shipped files' hashes for this release")
    hashes.add_argument("--check", action="store_true", help=CHECK_HELP)
    hashes.add_argument("--root", default=".", help=ROOT_HELP)
    hashes.set_defaults(func=run_hashes)
    return top


def main(argv: list[str] | None = None) -> int:
    return run(sys.argv[1:] if argv is None else argv, parser=parser())


if __name__ == "__main__":
    sys.exit(main())
