"""Root containment for the `[paths]` fields, and for nothing else yet.

`validate_paths` iterates `config.paths.as_dict()`, so the guard covers exactly the fields of
`schema.Paths` and no others. Four path-shaped, repository-writable fields never reach
`contained()`: `ledger.code_roots`, `artifacts.local`, `memory.groups` and
`memory.index_extra`. A `stayfixed.toml` setting
`ledger.code_roots = ["../../../../etc", "/etc/passwd"]` loads without a murmur, while the same
strings under `[paths]` are refused. Until that changes, `stayfixed.ledger` and `stayfixed.memory`
must call `contained()` themselves on the fields they consume; widening the guard here would change
`Config`'s shape, so it belongs with the module that first reads those fields.

Two rules, not one: `PATH_VALUE` is the grammar half — what a value must match before it may be
printed anywhere, a report included — and `contained()` is the root half, deciding whether the
value may be written *here*. The same four unguarded fields above are unguarded by both.

**The component rule is `fsops`', and this module borrows it rather than restating it.**
`contained()` used to split the value with `Path(relative).parts`, which normalises an empty
component, a trailing slash and a leading `./` out of existence; `fsops` splits the raw string
and refuses all three. So `plan()` found nothing wrong with `docs//roadmap-history.md` and
`apply()` raised on it after ten artifacts and the manifest were already written, leaving a
repository `init` would not touch again. The two spellings agreed for four review rounds, which
is what a duplicated rule does until it does not.
`checked_components` is the single spelling now; the import goes subpackage-to-leaf, so `fsops`
stays the leaf the hook path depends on it being.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

from stayfixed.config.schema import Config
from stayfixed.errors import Refusal
from stayfixed.fsops import (
    REACHES_NO_FILE,
    UnsafePath,
    checked_components,
    names_component,
    names_control_directory,
    said,
)
from stayfixed.printed import PATH_VALUE


class PathEscape(Refusal):
    """A configured path that leaves the project root or passes through a symlink."""


def contained(
    root: Path,
    relative: str,
    *,
    allow_final_symlink: bool = False,
    resolved_root: Path | None = None,
) -> Path:
    try:
        # The empty path, an absolute path, `..`, `.` and an empty segment, all read off the
        # caller's own spelling — one rule, in `fsops`, so a value this function accepts is a
        # value the write can reach. `fsops` raises `UnsafePath`, an `OSError`, because a leaf
        # module owns no user-facing verdict; a configured path's verdict is a `Refusal`, and
        # the translation is all this line adds.
        parts = checked_components(relative)
    except UnsafePath as exc:
        raise PathEscape(str(exc)) from exc
    # Git's control directory is refused by the call above, at every depth and in any case, and
    # this is where that matters for a *configured* path: `contained()` is the function every
    # `[paths]` value and every caller-supplied path goes through, above the first write.
    # `validate_paths` asks the same question one key at a time so its refusal can name the key;
    # the rule itself is `fsops.names_control_directory` in both places, because a guard stated
    # twice is the defect this module was just repaired for.
    target = root.joinpath(*parts)
    for ancestor in [target, *target.parents]:
        if ancestor == root:
            break
        # Asked with `lstat` here and each fault given its answer, never left to
        # `Path.is_symlink()`, which raises on `ENAMETOOLONG` up to Python 3.13 and answers
        # `False` from 3.14: `attach` ended in an internal error on one interpreter and attached
        # on the other over the same overlay. A path that reaches no file holds no link to
        # follow. That includes one past the longest path, which only the descriptor walk every
        # write goes through reaches (`fsops.open_within`), and that walk refuses a link of its
        # own accord; a link above it whose target is too long is still asked, since `lstat`
        # does not follow the link it is asked about. Any other fault leaves the question
        # unanswered, which is a refusal: no path is contained until every ancestor is asked.
        try:
            mode = os.lstat(ancestor).st_mode
        except OSError as exc:
            if exc.errno in REACHES_NO_FILE:
                continue
            # By its place under the root and through `repr`, as the refusal below names its
            # ancestor, and in the fault's own words, never `str(exc)`, which carries the
            # absolute path.
            unasked = ancestor.relative_to(root).as_posix()
            raise PathEscape(
                f"{relative!r} cannot be checked for a symlink at {unasked!r} ({said(exc)})"
            ) from exc
        if stat.S_ISLNK(mode) and not (allow_final_symlink and ancestor == target):
            # Both through `repr`, which escapes every line break and control character: in a
            # checkout the ancestor's name is the repository's, and a caller may show this refusal
            # to a terminal or a CI runner. Both by their place under the root: the ancestor's
            # absolute path said where this machine keeps the tree and nothing about the tree,
            # and a command relaying the refusal (`overlay init`'s `left` line) printed that.
            # `ancestor` is below `root`, since the walk stops there.
            named = ancestor.relative_to(root).as_posix()
            raise PathEscape(f"{relative!r} passes through a symlink at {named!r}")
    # Defence in depth. The guards above refuse every escape a path string can express — the
    # empty path, an absolute path, any `..` component, and a symlink at any level between the
    # root and the target — so the comparison below is the net under them rather than the
    # guard itself. It is here for the path form nobody has anticipated; a caller validating
    # many paths against one root passes `resolved_root` so this resolve happens once.
    if resolved_root is None:
        resolved_root = root.resolve()
    resolved = target.parent.resolve() / target.name if allow_final_symlink else target.resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise PathEscape(f"{relative!r} resolves outside the project root")
    return target


# stayfixed's own directory in a project: the manifest, `.stayfixed/local/` (attach's ledger, the
# local-only note store, `[artifacts] local` artifacts) and the assessment. Spelled here, beside
# the loop that reserves it, because `config` imports no area and the scaffold engine, `attach`
# and `memory` all import `config`; `tests/config/test_paths.py` holds each of their paths to lie
# under it, so the two spellings cannot drift apart.
STAYFIXED_DIRECTORY = ".stayfixed"


def names_stayfixed_directory(relative: str) -> bool:
    """Whether any component of `relative` is stayfixed's own directory, spelled in any case.

    `fsops.names_component`, the test `fsops.names_control_directory` asks too, and for the same
    two reasons. Any depth:
    a package inside a monorepo initialised on its own keeps its own `.stayfixed/local/`, and a
    parent project's `[paths]` value must not reach that either. Any case: the default
    filesystems on macOS and Windows fold case, so `.stayfixed/local/attach.json` is the same
    file.
    """
    return names_component(relative, STAYFIXED_DIRECTORY)


# `PATH_VALUE` in words, for the refusal a person reads. Kept beside the one reader that prints
# it; a change to the grammar is a change to this sentence.
PATH_RULE = (
    "segments of letters, digits, `.`, `_` and `-` joined by single `/`, none of them `.` or "
    "`..`, the first not starting with `-`, and no `/` at either end"
)


def validate_paths(config: Config, root: Path) -> dict[str, Path]:
    resolved_root = root.resolve()
    for name, relative in config.paths.as_dict().items():
        if not PATH_VALUE.match(relative):
            # Named and never quoted: this is the value a report would otherwise print.
            # The rule in words, not `PATH_VALUE.pattern`: the lookahead that closes `.` and `..`
            # as segments is correct and is no sentence a person can act on.
            raise PathEscape(f"paths.{name} is not a plain relative path: {PATH_RULE}")
        if names_control_directory(relative):
            # Named and never quoted, for the same reason. Nothing reserved git's control
            # directory: the grammar admits a leading dot, and `contained()` refused an
            # absolute path, `..` and a symlink but not a directory. So a clone could set
            # `agents_md = ".git/hooks/pre-commit"` — a `MANAGED_REGION`, exempt from the
            # engine's "exists and stayfixed did not write it" guard — and have its own
            # executable pre-commit hook rewritten in place, mode and all.
            #
            # The anchor is the project root the CLI resolved, and `.git` is git's own name
            # inside it; the clone authors this value and nothing else, so it cannot move the
            # directory being reserved. `.git` and not "a leading dot", because
            # `.github/workflows/` is stayfixed's own footprint.
            raise PathEscape(
                f"paths.{name} names git's control directory, which is git's and not "
                "stayfixed's to write into"
            )
        if names_stayfixed_directory(relative):
            # Named and never quoted. `.stayfixed/` is where stayfixed keeps its manifest and, under
            # `.stayfixed/local/`, state git never sees: attach's ledger and the local-only notes.
            # A `[paths]` value is committed, and `agents-md` is a `MANAGED_REGION` inserted into
            # whatever file `agents_md` names, exempt from the "exists and stayfixed did not write
            # it" guard — so a pulled commit setting `agents_md = ".stayfixed/local/attach.json"`
            # had `upgrade` rewrite the ledger in a directory git cannot restore.
            #
            # The anchor is the project root the CLI resolved and `STAYFIXED_DIRECTORY` above, a
            # constant in the installed package; the clone authors the value and nothing else.
            # No configured path belongs there: the preset puts none, and every file stayfixed
            # keeps in it is found by a constant, never through `[paths]`.
            raise PathEscape(
                f"paths.{name} names stayfixed's own directory {STAYFIXED_DIRECTORY}, which holds "
                "its manifest and state git never sees and is not a place for a configured path"
            )
    return {
        name: contained(
            root,
            relative,
            allow_final_symlink=(name == "memory"),
            resolved_root=resolved_root,
        )
        for name, relative in config.paths.as_dict().items()
    }
