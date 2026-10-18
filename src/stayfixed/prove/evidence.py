"""Evidence records: one JSON line on the machine for every `stayfixed prove` and `stayfixed gate`
run, a log of what each run came to.

**Where.** `$XDG_STATE_HOME/stayfixed/evidence/<key>.jsonl` where `XDG_STATE_HOME` is set to an
absolute path, else `$HOME/.local/state/stayfixed/evidence/<key>.jsonl` where `HOME` is one: the
state home the XDG base directory specification names. Where neither is, no record. One file per
project, keyed by `project_key`: the repository's `origin`, normalised, so two clones of one
repository share a file, and else the real path of the checkout's top-level. No rotation and no
cap yet: a CI job adds two gate lines and one per `prove`, and a machine's runs grow the file by a
line each.

**What it is not.** A log, and nothing more: no gate, verdict or trust decision reads one, so the
variables that place it are no anchor and need be none. It is never written where a git checkout
would carry it, and a record that cannot be written (no state home, a state directory that is not
a directory or is a link, a full disk) is one warning on standard error, which changes neither the
verdict nor the exit code.

**Every control here, with its adversary and its anchor.**

- No record a git checkout would carry: a dotfiles checkout at the home, where the record would be
  an untracked file of that repository, whether the run answers for it or for a project nested in
  it; a checkout at the state directory; a `HOME` or `XDG_STATE_HOME` that a checkout's own direnv
  or devcontainer file points inside it. The adversary is an honest mistake, a commit that carries
  a machine's log, and the anchor is git's answer, asked from the nearest part of the evidence
  directory that exists: inside a checkout, the record is written only where `git check-ignore`
  answers that the checkout ignores it, so a dotfiles repository that ignores `.local/state` gets
  its records and no warning. A checkout that does not ignore it, or a `check-ignore` that gives
  no answer, is no record and a warning naming it (fail closed). A bare-repository dotfiles home
  (`--git-dir=~/.dotfiles`, no `.git` in the home) is past it: git names no checkout there unless
  told where its directory is.
- The write walks from the state home's base (`XDG_STATE_HOME`'s directory, or `HOME`) with
  `O_NOFOLLOW` (`fsops.open_within`, `fsops.append_at`): a link planted at the state directory or
  the record redirects nothing, and is a warning instead. The base itself (or, while it is not made
  yet, the nearest directory above it that is) is followed first, where it leads: a home moved to
  another disk and linked back is the machine's.
- Nothing here is an input to anything: whoever can write the record, the agent among them, writes
  only a log, which is why a failure to write one is a warning and never a refusal.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from stayfixed import __version__, fsops, gitenv
from stayfixed.printed import clipped
from stayfixed.prove import tree
from stayfixed.prove.run import Receipt

# The variables that name the state home, the specification's default for it under `HOME`, and
# the evidence directory under the state home.
XDG_STATE_HOME = "XDG_STATE_HOME"
HOME = "HOME"
HOME_STATE = ".local/state"
EVIDENCE_DIR = "stayfixed/evidence"
SUFFIX = ".jsonl"
# The record format's version, a key of every line (`json.dumps(sort_keys=True)` writes the keys in
# name order, so it is not the first one): a key added, renamed or removed is a new version, which
# a reader of the records can tell apart. `tests/prove/test_evidence.py` holds each kind of line's
# keys at this version.
VERSION = 1
# How long a key's digest is, in hex characters: 128 bits, more than enough to tell projects apart
# on one machine, short enough for a file name.
KEY_HEX = 32

# The one warning, said on standard error in place of a record.
NOT_RECORDED = "stayfixed: the evidence record {record} was not written: {why}"
# What the warning calls a record it cannot name: there is no state home to put it under.
UNNAMED = "of this run"
NO_HOME = "neither XDG_STATE_HOME nor HOME is set to an absolute path"
INSIDE_REPOSITORY = (
    "it would lie inside a git checkout that does not ignore it, and a record is never written "
    "where a checkout would carry it"
)
UNASKED = (
    "it would lie inside a git checkout, and git did not answer whether that checkout ignores it"
)

# The scp-like form git reads as ssh: `[user@]host:path`, with no `/` before the `:`.
_SCP = re.compile(r"(?:[^@/:]+@)?(?P<host>[^/:]+):(?P<path>.*)", re.DOTALL)
# The schemes one host and path are one repository over.
_NETWORK = frozenset({"ssh", "https", "http", "git", "git+ssh", "ssh+git"})
_FILE = "file"


@dataclasses.dataclass(frozen=True)
class StateHome:
    """Where records go: `base`, the directory the write's walk starts from, and `directory`, the
    evidence directory's path below it."""

    base: Path
    directory: str


def state_home(environ: Mapping[str, str]) -> StateHome | None:
    """`XDG_STATE_HOME` where it is an absolute path, else `HOME`'s `.local/state` where `HOME` is
    one, each with the evidence directory below it; `None` where neither is. A relative
    `XDG_STATE_HOME` is ignored, as the specification says."""
    state = environ.get(XDG_STATE_HOME, "")
    if os.path.isabs(state):
        return StateHome(Path(state), EVIDENCE_DIR)
    home = environ.get(HOME, "")
    if os.path.isabs(home):
        return StateHome(Path(home), f"{HOME_STATE}/{EVIDENCE_DIR}")
    return None


def _bare(path: str) -> str:
    """`path` without a trailing `/`, then `.git`, then `/`."""
    return path.rstrip("/").removesuffix(".git").rstrip("/")


def normalised_origin(url: str) -> str:
    """One spelling for every URL of one repository: userinfo and port dropped, a trailing `/`
    and `.git` dropped, the scheme and host lower-cased, the scp form `user@host:path` read as
    `ssh://host/path`, and the `ssh`, `https`, `http` and `git` URLs of one host and path read as
    one, `ssh://`. A local path, or a `file:` URL's path, is the path less its `.git`."""
    split = urlsplit(url)
    scheme = split.scheme.lower()
    if scheme in _NETWORK and split.hostname:
        return f"ssh://{split.hostname.lower()}/{_bare(split.path).lstrip('/')}"
    if scheme == _FILE:
        return _bare(split.path)
    if "://" not in url and not url.startswith(("/", ".")) and (scp := _SCP.fullmatch(url)):
        return f"ssh://{scp['host'].lower()}/{_bare(scp['path']).lstrip('/')}"
    return _bare(url)


def _digest(text: str | bytes) -> str:
    data = text.encode("utf-8") if isinstance(text, str) else text
    return hashlib.sha256(data).hexdigest()[:KEY_HEX]


def _top(root: Path) -> Path:
    """The checkout `root` lies in, or `root` itself outside one."""
    return gitenv.checkout_root(root) or root


def project_key(root: Path) -> str:
    """`origin-` and the digest of the checkout's normalised `origin`, else `path-` and the digest
    of the real path of the checkout's top-level (of `root` itself outside one). A git that cannot
    be asked at all keys by the path too: the record is a log and never stops a run."""
    try:
        origin = gitenv.origin_remote(root)
    except gitenv.GitUnavailable:
        origin = None
    if origin:
        return f"origin-{_digest(normalised_origin(origin))}"
    return f"path-{_digest(os.fsencode(os.path.realpath(_top(root))))}"


def planned(root: Path, home: StateHome) -> Path:
    """Where the record of the project at `root` goes under `home`."""
    return home.base / home.directory / f"{project_key(root)}{SUFFIX}"


def carried(record: Path) -> str | None:
    """Why a git checkout would carry `record`, or `None` where none would: asked from the nearest
    part of its directory that exists, so it holds the repository the run answers for, a dotfiles
    repository at the home and one at the state directory alike. Inside a checkout, only
    `check-ignore`'s "ignored" (exit 0) lets the record through; "not ignored" (exit 1) and no
    answer at all each say why not."""
    asked = fsops.creation_directory(record)
    if gitenv.checkout_root(asked) is None:
        return None
    relative = record.relative_to(asked).as_posix()
    code, _ = gitenv.git_run(asked, "check-ignore", "-q", "--", relative)
    if code == 0:
        return None
    return INSIDE_REPOSITORY if code == 1 else UNASKED


def shown(path: Path) -> str:
    """A record's path as the warning prints it."""
    return clipped(str(path))


def _warned(record: str, why: str) -> str:
    warning = NOT_RECORDED.format(record=record, why=why)
    print(warning, file=sys.stderr)
    return warning


def append(path: Path, line: Mapping[str, object], *, base: Path) -> str | None:
    """Append `line` to the record at `path`, which lies under `base`, as one JSON line with its
    keys sorted, in one `O_APPEND | O_NOFOLLOW` write reached from `base` by the contained walk,
    the directories made as the hook sink makes its own; `None`, or the warning it printed."""
    payload = (json.dumps(line, sort_keys=True) + "\n").encode("utf-8")
    relative = path.relative_to(base).as_posix()
    try:
        fsops.mkdirs_within(base, relative)
        with fsops.open_within(base, relative) as (dir_fd, name):
            fsops.append_at(dir_fd, name, payload)
    except OSError as exc:
        return _warned(shown(path), fsops.said(exc))
    return None


def keep(root: Path, line: Mapping[str, object], *, home: StateHome | None) -> str | None:
    """Append `line` to the record of the project at `root` under `home`, or warn why not.

    The walk starts at the base, or at the nearest directory above it that is there where an
    `XDG_STATE_HOME` is not made yet, followed to where it leads first: a home moved to another
    disk and linked back is the machine's, and the contained walk below refuses a link only past
    it."""
    if home is None:
        return _warned(UNNAMED, NO_HOME)
    there = home.base
    while not fsops.exists(there) and there != there.parent:
        there = there.parent
    start = Path(os.path.realpath(there))
    path = planned(root, StateHome(start / home.base.relative_to(there), home.directory))
    why = carried(path)
    if why is not None:
        return _warned(shown(path), why)
    return append(path, line, base=start)


def stamp() -> str:
    """Now, in UTC, to the second."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def prove_record(receipt: Receipt, *, at: str, version: str) -> dict[str, object]:
    """A `prove` run's record: the format's version, `kind`, when, which stayfixed, and every
    field of its receipt, whose `argv` already carries no value."""
    return {
        "version": VERSION,
        "kind": "prove",
        "at": at,
        "stayfixed": version,
        **dataclasses.asdict(receipt),
    }


def gate_record(
    gates: Mapping[str, str],
    *,
    mode: str,
    argv: Sequence[str],
    commit: str | None,
    dirty: bool | None,
    at: str,
    version: str,
) -> dict[str, object]:
    """A `gate` run's record: the format's version, `kind`, when, which stayfixed, the run's `mode`
    (`builtin`, `custom` or `all`), the gate's own flags, the tree's commit and whether it
    differed from it, and each gate's verdict word by name."""
    return {
        "version": VERSION,
        "kind": "gate",
        "at": at,
        "stayfixed": version,
        "mode": mode,
        "argv": list(argv),
        "commit": commit,
        "dirty": dirty,
        "gates": dict(gates),
    }


def record_prove(root: Path, receipt: Receipt) -> str | None:
    """Keep the record of a `prove` run that answered for `root`; `None`, or the warning."""
    line = prove_record(receipt, at=stamp(), version=__version__)
    return keep(root, line, home=state_home(os.environ))


def record_gate(
    root: Path, gates: Mapping[str, str], *, mode: str, argv: Sequence[str]
) -> str | None:
    """Keep the record of a `gate` run over `root`: `gates` each gate's verdict word, `mode` and
    `argv` as `gate_record` takes them; `None`, or the warning."""
    commit, dirty = tree.head(root)
    line = gate_record(
        gates, mode=mode, argv=argv, commit=commit, dirty=dirty, at=stamp(), version=__version__
    )
    return keep(root, line, home=state_home(os.environ))
