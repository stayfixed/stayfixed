"""Which `git` this project runs, the environment it is given, and the bound on how long it may
take.

One module because every caller needs the same rule, and being the same for all of them is the
point: a git answer must be a real one about the repository asked, never one an inherited
`GIT_DIR` produced. The hook path's toplevel query feeds the hook's project root
(`checkout_root` below), which every hook decision is derived from, so a query that inherited
the session's `GIT_DIR` or `GIT_WORK_TREE` would make every handler in the process answer for a
different repository than the one the user is sitting in; the memory store's queries decide
whose notes a session reads, and the same variable would choose another project's.

A leaf module: it imports `stayfixed.errors` and nothing else from `stayfixed`, so the hook path
pays no area import to reach it, and no caller has to import another's area to share the
constants.

**In a stayfixed the hook wrapper launched, `git` is never found through `PATH`.** A committed
`.claude/settings.json` `env` block can set `PATH` for every hook — Claude Code applies it, and
resolves a relative entry against the project (measured on 2.1.293) — so a bare `git` there was
whatever binary the clone ships. There `git_program` takes the first executable of
`GIT_CANDIDATES`, the absolute paths `hooks/run-hook.sh` takes its own `git` from, in the same
order, and hands it a `PATH` of those paths' directories and the system's (`trusted_path`) and
never an inherited entry: git runs helpers by name — the program a `filter.<driver>.process`
names, such as `git-lfs`, and a `core.fsmonitor` hook — and an inherited `PATH` would choose
those for an absolute `git` just the same. No candidate is no answer, as a `git` that cannot be
launched is, and never a lookup on `PATH`. The wrapper says it launched this process through
`HOOK_WRAPPER_VARIABLE`, and nothing else is asked: not whether a terminal is attached, since a
hook run by hand from one is still a hook. This rule covers the programs stayfixed runs; the
wrapper keeps an exported function from standing in for its own builtins, and what the shell
acts on before the wrapper's first line, `SHELLOPTS` with `PS4` or a loader variable, is the
harness's to filter (`SECURITY.md`).

**Anywhere else, `git` and its `PATH` are the environment's**, as they always were. At a
terminal that is the person's own shell, where a fixed list is what picks the Xcode shim at
`/usr/bin/git` on macOS over the working `git` they installed. A `stayfixed gate` step
in CI runs in the repository's own job, and in a command an agent runs through its shell tool
`PATH` has already chosen the `stayfixed` binary itself, so a fixed list would buy nothing there
and would cost a machine whose only `git` is under a Nix store or `/opt/local/bin` every answer.

**`HOME` is kept, and it chooses git's global configuration**: `$HOME/.gitconfig` and
`$HOME/.config/git/config`, whose `core.fsmonitor` names a program git runs on `status`,
`ls-files` and `diff`. It is kept so that the owner's `safe.directory` and excludes answer.
Claude Code does not apply `HOME` from a project's `env` block (`SECURITY.md`); what can set it
for a checkout — direnv, mise, a devcontainer — can set `PATH` too, and is the person's own
environment, the class `PATH` at a terminal is in. Every `GIT_CONFIG_*` variable and
`XDG_CONFIG_HOME` are dropped, which closes git's other doors to that configuration.

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

# Everything else is dropped, `GIT_DIR` and `GIT_WORK_TREE` above all. In a stayfixed the hook
# wrapper launched, `git_program` replaces `PATH` (the module docstring).
GIT_ENV_KEEP = ("PATH", "HOME", "LANG", "LC_ALL", "SYSTEMROOT")

# The variable `hooks/run-hook.sh` exports, with this value, immediately before it runs the
# launcher: "this process is one the hook wrapper launched", and the one thing `git_program` asks.
# The wrapper overwrites whatever value it inherited, so on the hook path no `env` block or parent
# can turn it off; set anywhere else, it can only make the `git` choice stricter, never looser.
# Spelled twice, here and in the wrapper; `tests/hooks/test_wrapper.py` holds the two equal.
HOOK_WRAPPER_VARIABLE = "STAYFIXED_HOOK_WRAPPER"
HOOK_WRAPPER_LAUNCHED = "1"

# Where `git` is taken from in a stayfixed the hook wrapper launched: the first of these that is
# executable, as the wrapper's `test -x` asks. The list `hooks/run-hook.sh` takes its own `git`
# from, in its order, and one list spelled twice, since a shell script cannot import it:
# `tests/test_git_run.py` holds the two equal. The machine owner's own installs come before
# `/usr/bin/git`, for the reason a `PATH` lookup is kept everywhere else, and nothing under `HOME`
# is on it, since `HOME` is the environment's too.
GIT_CANDIDATES: tuple[str, ...] = (
    "/opt/homebrew/bin/git",
    "/usr/local/bin/git",
    "/home/linuxbrew/.linuxbrew/bin/git",
    "/run/current-system/sw/bin/git",
    "/usr/bin/git",
    "/bin/git",
)
# What follows the candidates' own directories in the `PATH` git is handed there.
SYSTEM_PATH: tuple[str, ...] = ("/usr/bin", "/bin", "/usr/sbin", "/sbin")

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
# prompt in a non-interactive session, or a `direnv`, `mise` or devcontainer environment. In a
# stayfixed the hook wrapper launched none of those chooses the `git` a call runs or the `PATH` it
# is handed (the module docstring), and anywhere else whatever sets this variable can set `PATH`
# as readily, which chooses that `git` outright; so a repository that sets it gains a longer wait,
# and never an answer it could not have had without it. In a hook that wait can outlast the
# harness's own timeout on the entry, which ends the hook unanswered where the bound would have
# ended git with no answer, so the wait is capped, at `FLOOR_CEILING_SECONDS`.
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


def scrubbed_env(path: str | None = None) -> dict[str, str]:
    """The variables `GIT_ENV_KEEP` names, as this process has them, with `PATH` set to `path`
    when one is given: what `git_run` hands git, and `test attribute` the `tar` it runs."""
    if path is None:
        return {key: os.environ[key] for key in GIT_ENV_KEEP if key in os.environ}
    return {**scrubbed_env(), "PATH": path}


def launched_by_the_hook_wrapper() -> bool:
    """Whether `hooks/run-hook.sh` launched this process: `HOOK_WRAPPER_VARIABLE` holds exactly
    `HOOK_WRAPPER_LAUNCHED`. Read at every call, like the list below."""
    return os.environ.get(HOOK_WRAPPER_VARIABLE) == HOOK_WRAPPER_LAUNCHED


def trusted_path() -> str:
    """The `PATH` git is handed in a stayfixed the hook wrapper launched: the directory of each of
    `GIT_CANDIDATES`, once and in the list's order, then `SYSTEM_PATH`. Built from constants
    alone, so no entry of it is inherited, and the helpers an installed `git` runs by name —
    `git-lfs` beside a Homebrew `git`, `ssh` — are found where that `git` was."""
    directories = [os.path.dirname(candidate) for candidate in GIT_CANDIDATES]
    return os.pathsep.join(dict.fromkeys([*directories, *SYSTEM_PATH]))


@dataclass(frozen=True)
class GitProgram:
    """The `git` a `git_run` call executes, and the `PATH` it is handed: `None` hands on this
    process's own."""

    executable: str
    path: str | None


def git_program() -> GitProgram | None:
    """The `git` to run here, or `None` in a hook when no candidate is executable.

    In a stayfixed the hook wrapper launched, the first of `GIT_CANDIDATES` that is executable,
    with `trusted_path`; the first that exists is *the* `git`, as in `hooks/run-hook.sh`, and one
    that then fails to answer is no answer rather than a reason to try the next. Anywhere else,
    `git` through this process's `PATH`, which git is handed as it is. Read at every call, so a
    test that changes the variable or the list is under its own choice from its next call.
    """
    if not launched_by_the_hook_wrapper():
        return GitProgram("git", None)
    for candidate in GIT_CANDIDATES:
        if os.access(candidate, os.X_OK):
            return GitProgram(candidate, trusted_path())
    return None


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
    ones. The `git` and the `PATH` it is handed are `git_program`'s: in a stayfixed the hook
    wrapper launched, an absolute candidate and a `PATH` of fixed directories, so a `PATH` a
    repository commits chooses neither git nor a helper git runs by name; anywhere else, the
    environment's own. A non-zero exit is returned, not collapsed — `check-ignore` answers 1 for
    "nothing matched", and that is an answer.

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

    No answer is three things, and `NO_ANSWER` names all three: git could not be launched —
    in a hook, no candidate is executable — it ran past `timeout`, or `stdin` held a
    character the filesystem's codec has no bytes for: a name from a note or a file written in
    UTF-8, asked on Linux under a locale that is not. A name read off the disk never does,
    because it was decoded with that same codec.
    """
    program = git_program()
    if program is None:
        return -1, ""
    codec = pipe_encoding()
    try:
        given = None if stdin is None else stdin.encode(codec, "surrogateescape")
        completed = subprocess.run(  # noqa: S603 - see the docstring
            [program.executable, "-C", str(root), *args],
            input=given,
            capture_output=True,
            check=False,
            timeout=max(timeout, bound_floor()),
            env=scrubbed_env(program.path),
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
    """Whether the `git` `git_run` runs here works at all, asked the same way.

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
