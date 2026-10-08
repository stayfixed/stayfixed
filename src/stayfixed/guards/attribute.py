"""Attribute one failing command to the change or to the environment, with evidence.

Three runs, never two: the working tree as it is (1), HEAD's committed tree extracted into a
scratch directory (2), and the merge-base with the base branch extracted the same way (3).
Between (2) and (3) the only variable is the code; between (1) and (2) the only variable is
the environment — provided the command syncs its own environment, which is the caller's to
arrange and the reason the command is an argument.

Run (3) needs one merge base, and a history can have several: each is as much "before this
change" as the others, a failure can pass on one and fail on another, and the one git picks
alone, the newest by date, is not the one the change forked from in any sense the others are
not. So several merge bases, like a shallow clone where the real one can be cut off and an older
commit stand in for it, leave the attribution undetermined: a `Failure` naming why, before
anything runs, and never a verdict read off a tree chosen for the reader.

Nothing here runs `git checkout`, `git stash` or `git reset`: `git archive` reads the object
database, and this module never writes the working tree or moves the checkout between
commits. Run 1 does execute the caller's command *in* the working tree, so whatever that
command writes there it writes — the guarantee is about this tool, not about that run.
"""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from stayfixed import fsops
from stayfixed.errors import Failure, Refusal
from stayfixed.findings import listed
from stayfixed.gitenv import NO_ANSWER, SHALLOW, ForkUnknown, fork_points, git_run, scrubbed_env
from stayfixed.runner import NOT_FOUND, TIMED_OUT, Completed, Runner

VERDICTS = (
    "pre-existing: the failure is on the merge-base too, so it is not this change",
    "this change: HEAD fails and the merge-base passes",
    "this change fixed a pre-existing failure: HEAD passes and the merge-base fails",
    "environmental: HEAD passes when synced and fails in the working tree as it is",
    "not reproduced: all three runs passed",
)


@dataclass(frozen=True)
class Attribution:
    head_ambient: int
    head_clean: int
    base_clean: int
    base: str
    merge_base: str
    verdict: str


def _executed(run: str, done: Completed) -> int:
    """The exit code of a run that ran; a timed-out or unlaunchable one is never scored."""
    if done.code in (TIMED_OUT, NOT_FOUND):
        raise Failure(
            f"the {run} run did not execute (code {done.code}: "
            f"{done.stderr.strip() or 'no output'}); narrow the command, or check it launches"
        )
    return done.code


def _verdict(ambient: int, head: int, base: int) -> str:
    if head != 0 and base != 0:
        return VERDICTS[0]
    if head != 0 and base == 0:
        return VERDICTS[1]
    if head == 0 and base != 0:
        return VERDICTS[2]
    if ambient != 0:
        return VERDICTS[3]
    return VERDICTS[4]


def _extract(root: Path, ref: str, into: Path) -> None:
    """`git archive REF` into a sibling file, then `tar -x` into `into`.

    The archive is written BESIDE the extraction directory, never inside it: a repository
    with a root-level `tree.tar` would otherwise have the archive overwrite itself mid-read.
    `git archive` honours the archived tree's own `.gitattributes` (`export-ignore`,
    `export-subst`), which are versioned too — so the extracted listing is compared to
    `git ls-tree -r --name-only REF`, and a difference is a `Failure` naming the likely cause
    rather than a silently smaller tree steering the verdict.

    **Both sides of that comparison are built the pedantic way, because every casual version
    of it made the check fire on ordinary repositories.** `-z` and a split on NUL, never
    `split()` and never `splitlines()`: `split()` breaks `sub dir/a b.txt` into three phantom
    entries, and plain `splitlines()` survives that but not git's own quoting — without `-z`,
    `ls-tree` renders a name carrying a quote or a non-ASCII byte as `"quo\"te.txt"` and
    `"\303\274n..."`, neither of which is the name on disk.

    And presence is **asked of each expected name**, never inferred from a walk of the
    extraction. A walk that kept files and symlinks still answered "missing" for a submodule
    gitlink, which `git archive` materialises as an empty directory and which is therefore
    neither — measured, so every submodule-bearing repository got this `Failure`. `exists()`
    answers for that directory and `is_symlink()` for a tracked dangling link, whose own
    special case disappears into the same line.
    """
    into.mkdir()
    archive = into.parent / f"{into.name}.tar"
    code, _ = git_run(root, "archive", "--format=tar", "-o", str(archive), ref, timeout=120)
    # `-1` is `git_run`'s "no answer" — not launched or past its bound — and not an exit
    # status: "exited -1" names no cause. A `Failure` and not the listing's skip below, because
    # there is no weaker answer available: nothing was extracted.
    if code == -1:
        raise Failure(f"{NO_ANSWER}, so `git archive {ref}` extracted nothing")
    if code != 0:
        raise Failure(f"`git archive {ref}` exited {code}; nothing was extracted")
    try:
        done = subprocess.run(  # noqa: S603
            # PATH on purpose: the machine owner's tar. `env=` for the same reason every other
            # subprocess in this tree scrubs -- `TAR_OPTIONS` and `TAPE` in the ambient
            # environment otherwise reach an extraction whose contents decide a verdict.
            ["tar", "-xf", str(archive)],  # noqa: S607
            cwd=into,
            capture_output=True,
            check=False,
            env=scrubbed_env(),
        )
    # A missing binary is a reported finding, never a traceback, because stayfixed installs no
    # external program it launches: `gitenv.git_run` answers `(-1, "")` on an `OSError` and `runner`
    # answers `Completed(NOT_FOUND, ...)`; this is the same rule for `tar`.
    except OSError as exc:
        raise Failure(f"extracting {ref}: tar could not be run ({exc})") from None
    archive.unlink()
    if done.returncode != 0:
        raise Failure(f"extracting {ref} exited {done.returncode}")
    # `timeout=120`, matching the `git archive` above, and for the same reason `gitenv` asks a
    # caller to pass its own bound: the default is documented there as the cap for "a local,
    # argument-free, read-only query … which neither touches the network nor grows with the
    # repository", and `ls-tree -r` is the one call in this module whose cost IS the
    # repository's size. On the five-second cap a large or slow-volume tree timed out, `git_run`
    # returned `(-1, "")`, the `code == 0 and missing` test below went False, and the
    # export-rule comparison was skipped with no note — so the verdict was then computed from a
    # tree that really was missing files. The author had already judged this tree big enough
    # to need more than the default when giving `git archive` its 120.
    code, listing = git_run(root, "ls-tree", "-r", "--name-only", "-z", ref, timeout=120)
    # `-z` prints a tracked name raw, and `git_run` decodes it losslessly: a latin-1 filename
    # committed on Linux is one more expected name, spelled as the extraction's own path, so it
    # can neither hide an export rule nor be reported missing when it is there.
    #
    # A listing git gave no answer for — it ran past its bound — is no listing at all, and the
    # comparison is skipped. Skipping is the right answer
    # rather than a cop-out: this comparison exists to catch an export rule, it cannot answer
    # that question about a listing it never read, and raising on it would be one more
    # over-eager `Failure` on a healthy tree — the defect this whole comparison has now
    # produced in three separate shapes.
    expected = {name for name in listing.split("\0") if name}
    missing = [
        name
        for name in expected
        if not fsops.exists(into / name) and not fsops.is_symlink(into / name)
    ]
    if code == 0 and missing:
        raise Failure(
            f"{ref}'s archive is missing {len(missing)} tracked file(s); the likely "
            f"cause is a `.gitattributes` export rule in that tree, and this tool cannot "
            f"compare a tree it did not get whole"
        )


def _merge_base(root: Path, base: str) -> str:
    """The one commit run (3) extracts, or a `Failure` saying why there is none.

    `gitenv.fork_points` names every merge base, or says why they are not known. More than one
    is undetermined: counting them and naming the first `findings.LISTED_LIMIT` is the report,
    and picking one would be a verdict about a tree nobody asked for.
    """
    forks = fork_points(root, base)
    if isinstance(forks, ForkUnknown):
        if forks.cause == SHALLOW:
            remedy = "; fetch the whole history (`git fetch --unshallow`) and run it again"
        elif forks.answered:
            remedy = f"; is {base} fetched, and is --root inside a checkout?"
        else:
            remedy = ""
        raise Failure(
            f"the attribution is undetermined: the merge base of HEAD and {base} is unknown "
            f"({forks.cause}){remedy}"
        )
    if len(forks) > 1:
        raise Failure(
            f"the attribution is undetermined: HEAD and {base} have {len(forks)} merge bases "
            f"({listed(forks)}), each as much before this change as the others, and a "
            f"failure can pass on one and fail on another; merge {base} into the change so its "
            f"tip is the one merge base, or pass `--base` naming the commit to compare against"
        )
    return forks[0]


def attribute(root: Path, *, command: str, base: str, runner: Runner) -> Attribution:
    if base.startswith("-"):
        raise Refusal("--base must name a ref, not an option")
    merge_base = _merge_base(root, base)
    ambient = _executed("working tree", runner.launch(["sh", "-c", command], root))
    with tempfile.TemporaryDirectory(prefix="stayfixed-attribute-") as scratch:
        head = Path(scratch) / "head"
        merge = Path(scratch) / "base"
        _extract(root, "HEAD", head)
        _extract(root, merge_base, merge)
        head_clean = _executed("head", runner.launch(["sh", "-c", command], head))
        base_clean = _executed("base", runner.launch(["sh", "-c", command], merge))
    return Attribution(
        ambient, head_clean, base_clean, base, merge_base, _verdict(ambient, head_clean, base_clean)
    )
