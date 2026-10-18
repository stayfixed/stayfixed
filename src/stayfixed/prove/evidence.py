"""Evidence records: one JSON line on the machine for every `stayfixed prove` and `stayfixed gate`
run, a log of what each run came to.

**Where.** `<home>/.local/state/stayfixed/evidence/<key>.jsonl`, the home being the password
database's entry for this process's user (`config.machine.passwd_home`): no `HOME`, `XDG_STATE_HOME`
or any other variable moves it, for the reason `config.machine` gives for the machine file, that a
checkout can set them. One file per project, keyed by `project_key`: the repository's `origin`,
normalised, so two clones of one repository share a file, and else the real path of the checkout's
top-level. No rotation and no cap yet: a CI job adds two gate lines and one per `prove`, and a
machine's runs grow the file by a line each.

**What it is not.** A log, and nothing more: no gate, verdict or trust decision reads one. It is
never written under a repository, and a record that cannot be written (no home, a state directory
that is not a directory or is a link, a full disk) is one warning on standard error, which changes
neither the verdict nor the exit code.

**Every control here, with its adversary and its anchor.**

- The home from the password database: a checkout that sets `HOME` or `XDG_STATE_HOME` (a direnv
  or devcontainer file) to put the record inside itself, where a later commit would carry it. The
  anchor is the database, which no variable moves.
- No record inside the repository the run answers for: a dotfiles checkout at the home itself,
  where the record would be a file of the repository. The anchor is git's answer for the top-level
  and the database's home; the run is unchanged and a warning names the record not written.
- The write walks from the home with `O_NOFOLLOW` (`fsops.open_within`, `fsops.append_at`): a link
  planted at the state directory or the record redirects nothing, and is a warning instead.
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
from stayfixed.config.machine import passwd_home
from stayfixed.printed import clipped
from stayfixed.prove import tree
from stayfixed.prove.run import Receipt

# Under the home, the machine's state directory for stayfixed, and the evidence directory in it.
STATE_DIR = ".local/state/stayfixed"
EVIDENCE = "evidence"
SUFFIX = ".jsonl"
# The record format's version, the first key of every line.
VERSION = 1
# How long a key's digest is, in hex characters: 128 bits, more than enough to tell projects apart
# on one machine, short enough for a file name.
KEY_HEX = 32

# The one warning, said on standard error in place of a record.
NOT_RECORDED = "stayfixed: the evidence record {record} was not written: {why}"
# What the warning calls a record it cannot name: there is no home to put it under.
UNNAMED = "of this run"
NO_HOME = "the password database lists no home directory for this user"
INSIDE_REPOSITORY = (
    "it would lie inside the repository this run answers for, and a record is never written there"
)

# The scp-like form git reads as ssh: `[user@]host:path`, with no `/` before the `:`.
_SCP = re.compile(r"(?:[^@/:]+@)?(?P<host>[^/:]+):(?P<path>.*)", re.DOTALL)
# The schemes one host and path are one repository over.
_NETWORK = frozenset({"ssh", "https", "http", "git", "git+ssh", "ssh+git"})
_FILE = "file"


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


def _planned(root: Path, home: Path) -> Path:
    return home / STATE_DIR / EVIDENCE / f"{project_key(root)}{SUFFIX}"


def _inside_repository(root: Path, home: Path) -> bool:
    """Whether `home` lies inside the repository `root` is in; never outside one."""
    top = gitenv.checkout_root(root)
    if top is None:
        return False
    return Path(os.path.realpath(home)).is_relative_to(os.path.realpath(top))


def record_path(root: Path, *, home: Path | None) -> Path | None:
    """The record of the project at `root` under `home`; `None` where there is no home, or where
    the record would lie inside the repository `root` is in."""
    if home is None or _inside_repository(root, home):
        return None
    return _planned(root, home)


def shown(path: Path) -> str:
    """A record's path as the warning prints it."""
    return clipped(str(path))


def _warned(record: str, why: str) -> str:
    warning = NOT_RECORDED.format(record=record, why=why)
    print(warning, file=sys.stderr)
    return warning


def append(path: Path, line: Mapping[str, object], *, home: Path) -> str | None:
    """Append `line` to the record at `path`, which lies under `home`, as one JSON line with its
    keys sorted, in one `O_APPEND | O_NOFOLLOW` write reached from `home` by the contained walk,
    the directories made as the hook sink makes its own; `None`, or the warning it printed."""
    payload = (json.dumps(line, sort_keys=True) + "\n").encode("utf-8")
    relative = path.relative_to(home).as_posix()
    try:
        fsops.mkdirs_within(home, relative)
        with fsops.open_within(home, relative) as (dir_fd, name):
            fsops.append_at(dir_fd, name, payload)
    except OSError as exc:
        return _warned(shown(path), fsops.said(exc))
    return None


def keep(root: Path, line: Mapping[str, object], *, home: Path | None) -> str | None:
    """Append `line` to the record of the project at `root` under `home`, or warn why not."""
    path = record_path(root, home=home)
    if home is None:
        return _warned(UNNAMED, NO_HOME)
    if path is None:
        return _warned(shown(_planned(root, home)), INSIDE_REPOSITORY)
    return append(path, line, home=home)


def stamp() -> str:
    """Now, in UTC, to the second."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def prove_line(receipt: Receipt, *, at: str, version: str) -> dict[str, object]:
    """A `prove` run's record: the format's version, `kind`, when, which stayfixed, and every
    field of its receipt, whose `argv` already carries no value."""
    return {
        "version": VERSION,
        "kind": "prove",
        "at": at,
        "stayfixed": version,
        **dataclasses.asdict(receipt),
    }


def gate_line(
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
    line = prove_line(receipt, at=stamp(), version=__version__)
    return keep(root, line, home=passwd_home())


def record_gate(
    root: Path, gates: Mapping[str, str], *, mode: str, argv: Sequence[str]
) -> str | None:
    """Keep the record of a `gate` run over `root`: `gates` each gate's verdict word, `mode` and
    `argv` as `gate_line` takes them; `None`, or the warning."""
    commit, dirty = tree.head(root)
    line = gate_line(
        gates, mode=mode, argv=argv, commit=commit, dirty=dirty, at=stamp(), version=__version__
    )
    return keep(root, line, home=passwd_home())
