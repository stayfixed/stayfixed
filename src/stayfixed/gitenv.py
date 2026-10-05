"""The environment every `git` this project runs is given, and the bound on how long it may take.

One module because every caller needs the same rule, and being the same for all of them is the
point: a git answer must be a real one about the repository asked, never one an inherited
`GIT_DIR` produced. The hook path's toplevel query feeds the hook's project root
(`checkout_root` below), which every hook decision is derived from, so a query that inherited
the session's `GIT_DIR` or `GIT_WORK_TREE` would make every handler in the process answer for a
different repository than the one the user is sitting in; the memory store's queries decide
whose notes a session reads, and the same variable would choose another project's.

A leaf module: it imports `stayfixed.errors` and nothing else from `stayfixed`, so the hook path
pays no area import to reach it, and no caller has to import another's area to share the
constant.

**`PATH` is here on purpose, and it is the one entry with a cost.** `git` is resolved through it
rather than pinned to `/usr/bin/git`, because the machine owner's `git` is the one that must
answer — a hardcoded path is what picks the Xcode shim on macOS over the working `git` they
installed. A committed `.claude/settings.json` `env` block can set `PATH` in a non-interactive
session, which is a harness-level exposure this module cannot close and does not pretend to.

`git_run` is the one runner for every question this project asks git about a repository it works on
— the hook path's toplevel, the three-valued answer (`git_answer`) the memory store and
`origin_remote` read and its usability probe, the hooks directory, the dirty count and the commit
range included. One decoding boundary, and a lossless one, so no byte of git's answer can raise out
of a command and each site decides only what an answer means to it. The
`Runner` seam in `stayfixed.runner`, which launches the owner's own commands — `git clone` among
them — for their exit code and a message, is the other. One question goes through that seam
and not through `git_run`, on purpose: `stayfixed overlay publish-template`, a maintainer
command, asks `git status --porcelain` of a scratch clone it has just filled with stayfixed's own
template, beside the `add`, `commit` and `push` it runs the same way, so its tests stub all four
at one seam. It only counts and reports the changed names, and the seam reads them with a
replacement character, so a name that is not UTF-8 cannot end it as an internal error.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from stayfixed.errors import Failure

# Everything else is dropped, `GIT_DIR` and `GIT_WORK_TREE` above all.
GIT_ENV_KEEP = ("PATH", "HOME", "LANG", "LC_ALL", "SYSTEMROOT")

# Wall-clock bound on one `git` call: a named cap (CONTRIBUTING.md#named-caps), and no shipped file
# changes with it. It is the bound for a local, argument-free, read-only query against the
# environment below (`rev-parse`, `remote get-url`, `--version`), which neither touches the network
# nor grows with the repository: it guards against a `git` binary that hangs outright, and is
# generous for that without leaving a hook blocked for long. A caller whose query is not that shape
# passes its own wider bound instead and says why beside it —
# `stayfixed.ledger.write.FETCH_TIMEOUT_SECONDS` for one that reaches the network,
# `QUERY_TIMEOUT_SECONDS` below for one that is merely slow, since a `log --all` over a long history
# is not a five-second `rev-parse`. Tune this number for the hang, not for a remote and not for a
# long history.
GIT_TIMEOUT_SECONDS = 5
# The wider bound on one local query that grows with the repository — a `log --all`, a `grep`
# over a long history, a listing of every tracked file — which neither reaches the network nor
# may be read as "nothing found" when it runs out: the ledger and the inventory's probes each
# read its `-1` as no answer.
QUERY_TIMEOUT_SECONDS = 30

# The one input that raises the least bound `git_run` gives a call, whatever bound its caller
# asked for. Unset, there is no floor, and each bound above, and each caller's own, is the one that
# applies. stayfixed's own test suite sets it (`tests/conftest.py`), in its own process and in every
# `stayfixed` it starts, so that a verdict does not turn on how loaded the machine running it is; a
# test about a bound running out removes it and passes a small bound of its own.
#
# **Why a variable here is safe.** It is read from this process's environment and from nothing a
# repository commits: no `stayfixed.toml` key, no machine-file key, no argument names it. It can
# only raise: `bound_floor` never answers below zero, and `git_run` takes the larger of it and the
# caller's bound, so no value of it shortens any bound, and one that is not a positive number is
# ignored. A repository reaches a process's environment only through something that applies a file
# it commits — a harness's `.claude/settings.json` `env` block, which applies without a trust
# prompt in a non-interactive session, or a `direnv`, `mise` or devcontainer environment — and
# every one of those sets `PATH` as readily, which chooses the `git` every call here executes (the
# module docstring). So a repository that sets this variable gains only a longer wait on a `git` it
# could replace outright. In a hook that wait can outlast the harness's own timeout on the entry,
# which ends the hook unanswered; what an unanswered hook lets through, the same file's own `git`
# lets through at once, by answering whatever a guard wants to hear. The wait is capped all the
# same, at `FLOOR_CEILING_SECONDS`.
FLOOR_VARIABLE = "STAYFIXED_GIT_FLOOR_SECONDS"
# Ten minutes: far above what any load makes a local `git` take, and far below a timeout that
# `subprocess` cannot represent — `timeout=1e300` raises `OverflowError`, which `git_run` does
# not catch, so an uncapped value would end every caller as an internal error.
FLOOR_CEILING_SECONDS: float = 600

# What `git_run`'s `(-1, "")` means, in one clause a caller's message can build on. The runner
# does not say which of the three it was, because none of them is an answer about the
# repository: a caller that words `-1` as one cause — "git is not installed", "the fetch timed
# out" — is wrong about the other two. What git printed is never one of them: its output is
# decoded losslessly, so an answer is always read.
NO_ANSWER = "git could not be run, ran past its time limit, or could not be given its input"


def bound_floor() -> float:
    """The least bound `git_run` gives a call now: what `FLOOR_VARIABLE` says when it says a
    positive number, never past `FLOOR_CEILING_SECONDS`, and zero otherwise.

    Read at every call rather than once at import, so a test that removes the variable is under
    the product's own bounds from its next call, in this process and in any it starts.
    """
    try:
        asked = float(os.environ.get(FLOOR_VARIABLE, ""))
    except ValueError:
        return 0.0
    # Written so that `nan`, which compares false with everything, falls to zero with the rest.
    if not asked > 0:
        return 0.0
    return min(asked, FLOOR_CEILING_SECONDS)


def in_work_tree(root: Path) -> bool:
    """Whether `root` or a directory above it holds a `.git` entry, which is how git itself finds
    the repository: a directory in a clone, a file in a worktree or a submodule.

    Read off the disk and never asked of git, because git refuses that question the same way it
    refused the one before it: a `rev-parse` that times out, or that exits 128 on a checkout it
    judges of dubious ownership (`safe.directory`) or on a worktree whose gitdir is gone, reads as
    "no repository" — and a guard that took that answer let its caller through. `GIT_DIR` is
    scrubbed from every `git` this project runs, so the `.git` entry is the one git would use.
    """
    return any(os.path.lexists(directory / ".git") for directory in (root, *root.parents))


def scrubbed_env() -> dict[str, str]:
    return {key: os.environ[key] for key in GIT_ENV_KEEP if key in os.environ}


def pipe_encoding() -> str:
    """The codec `git_run` decodes git's output and encodes its `stdin` with: the filesystem's,
    the one `os.fsdecode`, `Path.iterdir` and `sys.argv` use for the same names.

    Not the locale's. The two agree on Linux, where the filesystem codec follows the locale, and
    differ on macOS, where it is UTF-8 whatever `LC_ALL` says: under a latin-1 locale there, the
    locale's codec turns git's `café.md` into mojibake and sends a name on `stdin` to git as bytes
    that are not its own, so every comparison between git's answer and a path would miss — a
    gitignored document would read as not ignored. The error handler is `surrogateescape`, the
    filesystem's own on POSIX.

    Named once so `answer_bytes` undoes exactly what `git_run` did: where the codec is latin-1
    every byte decodes, so an answer carries no surrogate escape to show it was not UTF-8, and
    only re-encoding it with the same codec recovers the bytes git printed.
    """
    return sys.getfilesystemencoding()


def answer_lines(answer: str) -> list[str]:
    """A line-oriented `git_run` answer, split where git ended each line: at `\\n` alone.

    Never `str.splitlines()`, which also breaks at `\\r`, `\\v`, `\\f`, `\\x1c` to `\\x1e`,
    `\\x85` and the Unicode line and paragraph separators — characters git prints raw inside a
    path — so a worktree at `…/wt\\rx` would be listed as `…/wt`, a directory that is not it. A
    single-line answer is `answer.removesuffix("\\n")` for the same reason, and never `strip()`,
    which takes a trailing space or `\\r` off a path that ends in one. No answer is no lines.
    """
    lines = answer.split("\n")
    if lines[-1] == "":
        lines.pop()
    return lines


def answer_bytes(answer: str) -> bytes:
    """The bytes git printed for a `git_run` answer, for a caller that must read them as UTF-8
    whatever the locale: decoding is lossless both ways and nothing translates a line ending,
    so this is exact.
    """
    return answer.encode(pipe_encoding(), "surrogateescape")


def git_run(
    root: Path, *args: str, timeout: float = GIT_TIMEOUT_SECONDS, stdin: str | None = None
) -> tuple[int, str]:
    """`(returncode, stdout)` of `git -C root args`; `(-1, "")` when git gave no answer.

    The one place this project runs `git` to ask it something: every argument list is built
    from constants by the caller, every pathspec follows `--` or `--end-of-options`, and no
    configuration value reaches this list without `contained()` having refused the `-`-shaped
    ones. Resolved through PATH for the reason above: the machine
    owner's git must answer. A non-zero exit is returned, not collapsed — `check-ignore` answers
    1 for "nothing matched", and that is an answer.

    **Decoded with `surrogateescape`, both ways.** git speaks bytes, and a worktree path, a
    common directory, a name in `ls-files` or a ref can hold one the filesystem's codec cannot
    decode — a latin-1 filename on Linux. Strict decoding would raise `UnicodeDecodeError` out
    of every caller as an internal error, and reading such output as no answer would throw a
    real answer away, which a caller that takes "no answer" for "nothing" turns into a pass of
    what it should refuse. Escaped, and in the
    filesystem's codec (`pipe_encoding`), a byte comes back as the same `str` `os.listdir` and
    `sys.argv` give for it, so an answer is compared with, and opens, the path it names, and a
    name read off the disk goes back to git on `stdin` as its own bytes.

    **In bytes, and decoded here rather than by `subprocess`.** Text mode translates line endings
    on the way in: each `\\r\\n` and each lone `\\r` in git's answer would come back as `\\n`, so
    a name holding a carriage return, printed raw by every `-z` query, would come back as a
    different name, and a gitignored plan so named would read as not ignored. Nothing is
    translated, either way, and git's own stderr, which nobody reads, is never decoded.

    The answer is lossless rather than a placeholder, so every caller still decides about the
    path that is really there. What it does not make safe is writing that `str` into a UTF-8
    file or parsing it as UTF-8 text: a caller whose answer ends up in one checks it itself, as
    `assess.rule.read_base` does for the base's `stayfixed.toml`.

    No answer is three things, and `NO_ANSWER` names all three: git could not be launched, it
    ran past `timeout`, or `stdin` held a character the filesystem's codec has no bytes for: a
    name from a note or a file written in UTF-8, asked on Linux under a locale that is not. A
    name read off the disk never does, because it was decoded with that same codec.
    """
    codec = pipe_encoding()
    try:
        given = None if stdin is None else stdin.encode(codec, "surrogateescape")
        completed = subprocess.run(  # noqa: S603 - see the docstring
            ["git", "-C", str(root), *args],  # noqa: S607 - PATH on purpose, see the module docstring
            input=given,
            capture_output=True,
            check=False,
            timeout=max(timeout, bound_floor()),
            env=scrubbed_env(),
        )
    except (OSError, subprocess.SubprocessError, UnicodeEncodeError):
        return -1, ""
    answer = completed.stdout.decode(codec, "surrogateescape")
    return completed.returncode, answer


def _git_toplevel(cwd: Path) -> Path | None:
    """The checkout git names for `cwd`, as the path on disk, or `None` when git named none.

    Through `git_run`, which scrubs the environment because the answer must be a real git answer,
    not one an inherited `GIT_DIR` produced, and `checkout_root` feeds *every* hook decision, so
    an inherited `GIT_DIR` or `GIT_WORK_TREE` would make every handler answer for a different
    repository than the session is in. It also decodes
    the answer losslessly, so on Linux a checkout under a directory named in latin-1 bytes is
    that directory; decoded strictly, it would make every hook an internal error, which
    PreToolUse turns into a refusal of every tool call. The line ending alone is taken off, so a
    path that ends in a space is still that path.
    """
    code, out = git_run(cwd, "rev-parse", "--show-toplevel")
    top = out.removesuffix("\n")
    return Path(top) if code == 0 and top else None


def _walk_to_git_root(cwd: Path) -> Path | None:
    """`.git` is a directory in a clone and a file in a worktree or a submodule; both count.

    `git rev-parse --show-toplevel` resolves symlinks in `cwd` before it reports the toplevel,
    so the walk must too: otherwise the same repository reached through its real path and
    through a symlink to it would report two different roots where git collapses them into one.
    """
    if not cwd.is_absolute():
        return None
    for directory in [cwd, *cwd.parents]:
        if (directory / ".git").exists():
            return directory.resolve()
    return None


def checkout_root(cwd: Path) -> Path | None:
    """The checkout `cwd` sits in: a walk for `.git`, else git itself; `None` if neither names one.

    The hook's project root when no registered harness's variable names one, which makes this
    Codex's hot path: `stayfixed hook` runs as a subprocess on every tool call, and `git
    rev-parse --show-toplevel` costs about 8 ms of a 33 ms invocation where the walk costs about
    0.004 ms. git stays behind the walk for what a walk cannot see, such as `GIT_DIR` and a bare
    repository. It reads no harness variable: those are the registry's
    (`harnesses.Harness.project_dir_env`), and `hooks.dispatch.read_event` asks them first.
    """
    return _walk_to_git_root(cwd) or _git_toplevel(cwd)


class GitUnavailable(Failure):
    """`git` could not be run at all, or answered with an error.

    Distinct from "git ran and said no", and the distinction is the whole point of the class.
    A reader that took "could not ask" for "the answer is nothing" tells the user to run
    `stayfixed attach` when the real fault is their `git` — the state a macOS machine is in when
    `/usr/bin/git` is the Xcode shim with an unaccepted licence, since `GIT_ENV_KEEP` scrubs
    `DEVELOPER_DIR`.
    """


def git_is_usable(root: Path) -> bool:
    """Whether the `git` on this PATH works at all, asked with the same scrubbed environment.

    The discriminator for a non-zero exit, and the reason this is a second call rather than a
    guess at exit codes. `git` answers "no" with a non-zero exit in ordinary, correct
    situations — 128 for "not a git repository", 2 for "no such remote" — and a broken install
    also exits non-zero, so the number alone cannot tell the two apart: the Xcode shim with an
    unaccepted licence exits non-zero for every invocation, including `--version`. Asking a
    question that needs no repository separates "git said no" from "git cannot speak".

    Asked from `root`, as the question that failed was, so a `root` git cannot enter is "cannot
    speak" here too, as it was when the first question could not be launched there at all.

    One probe for every reader that has to tell the two apart — `git_answer` below, which
    `origin_remote` and the memory store read — so they cannot disagree about which `git` is
    broken. Not cached. It runs only after a query has already failed, and caching it would make the
    answer depend on which test ran first.
    """
    return git_run(root, "--version")[0] == 0


@dataclass(frozen=True)
class GitAnswer:
    """git's one-line answer to one question, in three values: an answer, no answer, or could
    not ask.

    `value` is the answer when there is one. `ran` is False only when `git` could not be run, or
    exited non-zero and `git_is_usable` says it cannot speak at all — an empty stdout from a
    successful run, and a refusal from a `git` that works, are "no answer", which is a fact about
    the repository rather than about the machine.
    """

    value: str | None
    ran: bool = True

    @property
    def unavailable(self) -> bool:
        return not self.ran

    def require(self, refusal: str) -> str | None:
        """The answer, raising `GitUnavailable(refusal)` rather than answering `None` when `git`
        could not be asked. The words are the caller's, because only the caller knows what went
        unanswered and what that stops."""
        if not self.ran:
            raise GitUnavailable(refusal)
        return self.value


def git_answer(root: Path, *args: str) -> GitAnswer:
    """git's one-line answer to `args` asked in `root`, through `git_run`.

    `git_run` scrubs the environment and decodes losslessly, so an `origin` URL holding a byte
    that is not UTF-8 is still an answer `init --questions` and `init --yes` can read: the
    answer is what git printed, a path as the filesystem spells it, less its line ending
    alone — never `strip()`, for `answer_lines`'s reason.
    """
    code, out = git_run(root, *args)
    if code == -1:
        return GitAnswer(None, ran=False)
    if code != 0:
        # `git` ran and declined, *or* `git` is broken. `git_is_usable` is what tells them
        # apart; without it every reader would take the second for the first.
        return GitAnswer(None, ran=git_is_usable(root))
    return GitAnswer(out.removesuffix("\n") or None)


def origin_remote(root: Path) -> str | None:
    """This checkout's `origin` URL, or `None` when `git` ran and there is no such remote.

    Public because `attach` compares it against the overlay's record and `init` derives a name
    from it, and neither may reach for a `subprocess.run` of its own: `git_run` scrubs `GIT_DIR`
    and `GIT_WORK_TREE`, and an inherited one would make the answer one about a different
    repository than the session is in. Two areas asking one question two ways is how they stop
    agreeing.

    A URL in bytes that are not UTF-8 is answered, as the filesystem's codec spells it, and not
    raised: it never equals a URL read out of a TOML file, so the binding reads as not this
    repository's, and `attach`, which would write it into one, refuses it by name. The answer is
    what git printed less its line ending alone, never `strip()`, for `answer_lines`'s reason.

    Raises `GitUnavailable` rather than answering `None` when `git` could not be asked at all.
    "No origin remote" is a fact about the repository and reads as *not this one*, while "could
    not ask" is a fault on this machine, and collapsing them tells the user to run `stayfixed
    attach` about their own `git`. A non-zero exit is either, so `git_answer` has `git_is_usable`
    ask a second question that needs no repository from the same `root`: git answers "no such
    remote" with an exit of its own, and a broken install exits non-zero for everything.

    The value is repository-authored (principle 5): a clone chooses its own remote URL, so a caller
    that shows it wraps it first.
    """
    return git_answer(root, "remote", "get-url", "origin").require(
        "`git` could not read this repository's origin remote — the fault is on this "
        "machine rather than in the repository; check that `git` runs here"
    )


SHALLOW = (
    "this clone is shallow, so the commits HEAD forked from can be cut off and an older one "
    "stand in for them"
)
DISJOINT = "HEAD and the base share no commit"


@dataclass(frozen=True)
class ForkUnknown:
    """Why the commits HEAD forked from a base at are not known: `cause` in words, and whether
    git answered at all, since a git that gave no answer sends a reader to a different remedy
    than a clone that is shallow or a base it refused."""

    cause: str
    answered: bool

    @classmethod
    def of(cls, code: int) -> ForkUnknown:
        """A question git exited `code` on. Any negative code is no answer: `git_run`'s `-1`,
        and a git a signal ended, which `subprocess` reports as the signal's negative."""
        if code < 0:
            return cls(NO_ANSWER, answered=False)
        return cls(f"git exited {code}", answered=True)


def fork_points(root: Path, base: str) -> list[str] | ForkUnknown:
    """Every commit HEAD forked from `base` at — `git merge-base --all <base> HEAD`, each best
    common ancestor, in git's order — or why they are not known.

    Every one, because a history the change shapes itself can have several, and the one git
    picks alone, the newest by date, is not the fork point in any sense the others are not: a
    reader of one answers about a tree the change can choose. Whether the clone is shallow is
    asked first, and a question git does not answer is not "not shallow": in a shallow clone the
    fork point can be cut off and an older commit be what git names. A shallow clone, one git
    will not answer about, and a base that shares no commit with HEAD are all not known. What
    that means, and what to do about it, each caller says in its own words; the base is refused
    by the caller when it is shaped like an option, before this is asked.
    """
    code, out = git_run(root, "rev-parse", "--is-shallow-repository")
    if code != 0:
        return ForkUnknown.of(code)
    if out.strip() == "true":
        return ForkUnknown(SHALLOW, answered=True)
    code, out = git_run(root, "merge-base", "--all", base, "HEAD")
    forks = out.split()
    if code == 1 and not forks:
        return ForkUnknown(DISJOINT, answered=True)
    if code != 0 or not forks:
        return ForkUnknown.of(code)
    return forks
