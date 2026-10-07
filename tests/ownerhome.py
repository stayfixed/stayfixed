"""The password database's answer for this user's home directory, as a test chooses it.

Every command that is not run by a person at a terminal takes the machine owner's home directory
from the password database and not from `HOME` (`stayfixed.config.machine.owner_home`). So a
`HOME` under `tmp_path` no longer keeps such a command away from the developer's own
`~/.config/stayfixed`: the suite has to choose the database's answer too.

**In this process,** `follows_home` and `as_owner_home` replace `pwd.getpwuid` for the length of
one test. `tests/conftest.py` has the database follow `HOME` for every test, and a test about the
two homes differing pins it to another directory.

**In a process a test starts,** nothing in this process reaches it, and no variable can: the
point is that no variable moves that home. The smoke scripts' prelude is the seam
instead (`scripts/smoke_hooks.py`, `owner_home_prelude`). `stayfixed_argv` runs it ahead of the
command line. `checkout_with_owner_home` puts it where a `PYTHONPATH` entry runs it at start-up,
for a command whose argv a test does not write. `plugin_root_with_owner_home` puts it in front of
the launcher of a plugin root, for the wrapper, whose interpreter starts under `-I` and reads no
`PYTHONPATH`.
"""

from __future__ import annotations

import functools
import os
import pwd
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

from tests.scriptload import SCRIPTS, load

ROOT = Path(__file__).resolve().parents[1]


@functools.cache
def _smoke_hooks() -> ModuleType:
    return load(SCRIPTS / "smoke_hooks.py", "smoke_hooks_for_owner_home")


def entry_with_home(
    uid: int, home: str, lookup: Callable[[int], pwd.struct_passwd] = pwd.getpwuid
) -> pwd.struct_passwd:
    """This user's password entry with `home` as its home directory.

    Built on the real entry where there is one, so the name and shell stay this machine's; a
    container user the database does not list gets a made-up name, which nothing here reads.
    """
    try:
        real = tuple(lookup(uid))
    except KeyError:
        real = ("stayfixed-test", "x", uid, os.getgid(), "", "", "/bin/sh")
    return pwd.struct_passwd((*real[:5], home, *real[6:]))


def follows_home(monkeypatch: pytest.MonkeyPatch) -> None:
    """Have the password database record whatever `HOME` holds when it is asked.

    The ordinary machine, where the two agree, and what every test gets (`tests/conftest.py`): a
    test that plants a machine file under a `HOME` of its own keeps reading it. A test about the
    two disagreeing says so with `as_owner_home`.
    """
    real = pwd.getpwuid

    def lookup(uid: int) -> pwd.struct_passwd:
        return entry_with_home(uid, os.environ.get("HOME", ""), real)

    monkeypatch.setattr(pwd, "getpwuid", lookup)


def as_owner_home(monkeypatch: pytest.MonkeyPatch, home: Path | str | None) -> None:
    """Have the password database record `home` for this user, or no entry at all for `None`."""
    real = pwd.getpwuid

    def lookup(uid: int) -> pwd.struct_passwd:
        if home is None:
            raise KeyError(f"getpwuid(): uid not found: {uid}")
        return entry_with_home(uid, str(home), real)

    monkeypatch.setattr(pwd, "getpwuid", lookup)


def stayfixed_argv(home: Path) -> list[str]:
    """The argv of a `stayfixed` run from this checkout with the database recording `home`, as
    `scripts/stayfixed` runs it; the command's own arguments follow."""
    bootstrap = (
        f"{_smoke_hooks().owner_home_prelude(home)}"
        f"import sys\nsys.path.insert(0, {str(ROOT / 'src')!r})\n"
        "from stayfixed.cli import main\nraise SystemExit(main())\n"
    )
    return [sys.executable, "-c", bootstrap]


def checkout_with_owner_home(into: Path, home: Path) -> Path:
    """This checkout again at `into`, every entry a link to its own, except that `src` is a
    directory beside the package whose `sitecustomize` has the database record `home`: a
    `stayfixed` run with `PYTHONPATH=<into>/src` and without `-I` runs it at start-up."""
    into.mkdir(parents=True)
    for entry in ROOT.iterdir():
        if entry.name != "src":
            (into / entry.name).symlink_to(entry, target_is_directory=entry.is_dir())
    (into / "src").mkdir()
    (into / "src" / "stayfixed").symlink_to(ROOT / "src" / "stayfixed", target_is_directory=True)
    (into / "src" / "sitecustomize.py").write_text(
        _smoke_hooks().owner_home_prelude(home), encoding="utf-8"
    )
    return into


def plugin_root_with_owner_home(base: Path, home: Path, source: Path = ROOT) -> Path:
    """`source` as a plugin root under `base`, with the database's home pinned to `home`; built
    once, and the same root on every later call for the same `base`."""
    into = base / "owner-home-plugin"
    if into.exists():
        return into
    root: Path = _smoke_hooks().with_owner_home(source, into, home)
    return root
