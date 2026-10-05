"""The recording `stayfixed.runner.Runner` doubles the suite hands the code under test.

`Recorder` answers any program from a script, and `LsRemote` is `git ls-remote --exit-code`.
A module states what its runner answers at the call site, as keyword arguments, and keeps no
private runner class of its own unless the question it asks is not "record the argv and answer
from a script": `tests/guards/test_attribute.py`'s `_Coded` (answers by the tree it is run in) and
`tests/overlay/test_publish.py`'s `_GitHub` (models a repository's state) are the two that are
not, and each says why.

`git_that_cannot_run` is here too, though it is no `Runner`: the product runs `git` through
`gitenv.git_run` rather than a `Runner`, and a `git` that cannot be launched is a double every
module asking about one needs alike.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from stayfixed.release.pins import NO_MATCH
from stayfixed.runner import Completed


@dataclass(kw_only=True)
class Recorder:
    """Records every argv and working directory, and answers from a script or else the default.

    `answers` maps an argv prefix, written as its words joined by single spaces, to its answer;
    the longest key whose words equal the argv's leading elements wins, so a key of `gh` means
    "this binary" and a longer key scripts a single question — script one call by naming enough
    of its argv to tell it from its neighbours. The comparison is word for word, so an argv
    element that itself holds a space is never matched by a key. An argv no key matches gets
    `Completed(code, stdout, stderr)`.

    `on_call` runs before the answer is chosen, for a fixture that must exist by the time the code
    under test reads it — a template's files where `gh repo create --clone` would have put them.

    `calls` and `cwds` are what the double observed, in call order, and are not parameters.
    """

    code: int = 0
    stdout: str = ""
    stderr: str = ""
    answers: dict[str, Completed] = field(default_factory=dict)
    on_call: Callable[[list[str], Path], None] | None = None
    calls: list[list[str]] = field(default_factory=list, init=False)
    cwds: list[Path] = field(default_factory=list, init=False)

    def launch(self, argv: list[str], cwd: Path) -> Completed:
        self.calls.append(argv)
        self.cwds.append(cwd)
        if self.on_call is not None:
            self.on_call(argv, cwd)
        chosen: tuple[int, Completed] | None = None
        for key, answer in self.answers.items():
            words = key.split(" ")
            if argv[: len(words)] == words and (chosen is None or len(words) > chosen[0]):
                chosen = (len(words), answer)
        if chosen is not None:
            return chosen[1]
        return Completed(self.code, self.stdout, self.stderr)


# `LsRemote.code`'s default, which no process exits with: "derive the code from the listing".
_FROM_LISTING = -1


@dataclass(kw_only=True)
class LsRemote(Recorder):
    """`git ls-remote --exit-code` answering from a listing, with no network.

    The exit code follows git's contract unless the case names one: `NO_MATCH` for an empty
    listing and `0` for any other. So `LsRemote()` is "no tags", `LsRemote(stdout=listing)` is a
    listing, and `LsRemote(code=128)` or `LsRemote(code=NOT_FOUND)` is a git that failed. A case
    *about* the no-match branch spells `code=NO_MATCH`, so the value that selects the branch is
    visible in it.
    """

    code: int = _FROM_LISTING

    def __post_init__(self) -> None:
        if self.code == _FROM_LISTING:
            self.code = 0 if self.stdout else NO_MATCH


def git_that_cannot_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """A `git` that cannot be launched at all, the state `gitenv.GitUnavailable` is about, patched
    at the one seam the product runs it through: `gitenv.git_run`, which `git_answer`,
    `origin_remote` and `git_is_usable` all call inside `gitenv`.

    Patched rather than arranged, because the alternative is removing `git` from `PATH` for the
    whole process. A repository with no `origin` remote is a different state — `git` ran and
    answered nothing — and it is the ordinary "not bound" one rather than a machine fault.
    """

    def refuse(*args: object, **kwargs: object) -> tuple[int, str]:
        return -1, ""  # `git_run`'s own answer for a `git` that could not be launched

    monkeypatch.setattr("stayfixed.gitenv.git_run", refuse)
