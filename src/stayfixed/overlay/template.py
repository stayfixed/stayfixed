"""Where the shipped overlay tree is, and what `plan()` is handed for it.

`templates/overlay/` lives **under the module root**, beside `presets/`, and for the same
reason: it is read at *runtime* — `overlay create --local` renders it — so the copy that has to
answer is the one an installed stayfixed carries. The conventional plugin layout puts the tree at
the plugin root, and this repository has already departed from that layout once, for
`presets/recommended.toml`, which `load_preset` reads out of the package. Two facts settle it
here. `uv_build` has no wheel includes at all: "all data files must either be under the module
root or in the appropriate data directory", so `source-include` reaches the sdist and nothing
else. And `--local` is the fallback for an unreachable template repository, while the skills
reference the CLI by name — so the copy that runs is the one on `PATH`, and a fallback absent
from the wheel is not a fallback.
`hooks/` stays at the plugin root, because the *harness* reads it from there and Python never
does.

`template_root()` is still a function rather than a constant, because `resources.files` is what
answers for an installed package and a checkout alike. **There is no checkout fallback**, and
that is the point of the move: an earlier revision carried one, copying the scaffold engine's
checkout probe, since deleted, and its `parents[3]` arithmetic into this area — a second
spelling of one rule, across two areas, and after the move an unreachable one. A source
checkout is an `src/` layout, so `resources.files("stayfixed")` answers `src/stayfixed` there and
the tree is under it; there is no arrangement left in which the package probe misses and a
repository-root walk would have found it.
"""

from __future__ import annotations

from functools import partial
from pathlib import Path

from stayfixed.errors import Failure
from stayfixed.overlay.layout import OVERLAY_FILES, RETIRED_MEMORY_README
from stayfixed.scaffold import Kind, Template
from stayfixed.templates import tree

OVERLAY = "overlay"

# Every file an earlier release shipped and this one does not, which `overlay upgrade` and
# `overlay init` remove where it still holds what stayfixed wrote: the sha256 of each copy a
# release shipped there, and the way out for a copy kept because it holds other bytes. An overlay
# generated from a template carries no ledger (`publish-template` strips it), so these digests are
# the only evidence that such an overlay's copy is stayfixed's to remove.
#
# The memory README is the same bytes in 0.1.0 and 0.1.1. The template's own `attach` skill, a
# subset of the plugin's, which also covers detaching and a moved remote, is the same bytes in
# 0.1.0, 0.1.1 and 0.2.0. The README of `common/rules/`, a directory nothing read, is one file in
# 0.1.x and another in 0.2.0, which said so. `tests/overlay/test_upgrade.py` holds each copy whole,
# and `tests/overlay/test_template.py` holds that none of these is a file the template ships.
_RETIRED = {
    RETIRED_MEMORY_README: (
        frozenset({"407236dd35a9c1810465b8460271379fc54036b76d4bf64c0f1947eef0fe7322"}),
        "rename it to `_README.md`, or the note reader reads it as a note",
    ),
    "skills/attach/SKILL.md": (
        frozenset({"845e67006aa4303a2c69d1601c987f58ca28acf806f2e89f272b63ae8bb572c9"}),
        "the plugin's own `attach` skill replaces it; delete this copy once you no longer need "
        "your edits",
    ),
    "common/rules/README.md": (
        frozenset(
            {
                "926060a042a6ab26f407fbe7fe84bf30771d8c279fdbce49848f051d710443d9",
                "62b01f752ee77c3c8fb5fcc0b78b14907a3b98072ff3c9b7e76f6b792e7c065b",
            }
        ),
        "nothing read this directory; a standing rule is a note with `metadata.startup`, so move "
        "your rules into such notes and delete this copy",
    ),
}


def template_root() -> Path:
    """The directory `stayfixed/templates/overlay/` resolves to for this installation.

    A path is always returned, existing or not, so a caller that cannot find the tree can name
    where it looked instead of handling a `None`. `templates()` is the one place that becomes a
    refusal a user can act on. `stayfixed.templates.tree` is the one resolver both this tree and
    `project/`'s answer through, so the two cannot come to disagree about where "shipped"
    is — `resources.files` answers a `Path` for every filesystem install, which is every install
    this project supports; `fsops` contains writes with `dir_fd=` and `O_NOFOLLOW`, so a
    zip-imported stayfixed could not write an overlay in any case.
    """
    return tree(OVERLAY)


def _render(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def templates() -> list[Template]:
    """One whole-file `Template` per shipped file, rendered from the tree at apply time.

    Every artifact is `Kind.TEMPLATE`: the overlay is a repository stayfixed creates outright,
    so there is no file of somebody else's to merge a region or a keyed entry into. That is
    what makes `overlay upgrade` the engine's hash-and-skip rule rather than a second copy of
    it — an untouched file is refreshed, an edited one is skipped and named.
    """
    root = template_root()
    if not root.is_dir():
        raise Failure(
            f"the overlay template tree is not readable at {root}; this stayfixed was installed "
            "without it, so `--local` cannot render one"
        )
    return [
        Template(
            id=relative,
            kind=Kind.TEMPLATE,
            target=relative,
            source=f"{OVERLAY}/{relative}",
            render=partial(_render, root / relative),
        )
        for relative in OVERLAY_FILES
    ]


def retired() -> list[Template]:
    """One retired whole-file `Template` per file `_RETIRED` names.

    The engine removes such a file only when its bytes are stayfixed's: the digest the manifest
    records, or, with no record, one `_RETIRED` holds for what a release shipped. Any other copy
    is kept and named with its way out, since it may hold the owner's own words. `render` is
    never called for a retired file.
    """
    return [
        Template(
            id=relative,
            kind=Kind.TEMPLATE,
            target=relative,
            source=f"{OVERLAY}/{relative}",
            render=str,
            retired=True,
            shipped=shipped,
            remedy=remedy,
        )
        for relative, (shipped, remedy) in _RETIRED.items()
    ]
