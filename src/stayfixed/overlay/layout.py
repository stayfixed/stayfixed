"""What the overlay is called, directory by directory — names and nothing else.

A leaf module on purpose. `attach` needs to know where a project's record and a project's
notes sit inside the overlay, and it must be able to ask without importing a command module or
the scaffold engine; keeping the names here is what makes that possible.

`PROJECTS` and `PROJECT_RECORD` are **not** redefined here: they come from `stayfixed.memory.api`,
because `memory.store` already resolves this layout for the hook path and two spellings of one
layout is one more place for them to stop agreeing. `memory.store.COMMON` stays where it is for
the same reason in reverse — it is `Path("common") / "memory"`, that module's *path into* the
overlay rather than this module's *name for* a directory, and defining either in terms of the
other is how they would drift.
"""

from __future__ import annotations

from stayfixed.memory.api import PROJECTS

COMMON = "common"
COMMON_MEMORY = f"{COMMON}/memory"
COMMON_CLAUDE = f"{COMMON}/claude"
COMMON_CODEX = f"{COMMON}/codex"
# The overlay's identity record, at its root: what makes a tree a stayfixed overlay
# (`identity.overlay_fault`), and where the floor `requires.requires_of` reads is declared. It
# replaced the plugin manifests the overlay carried while it was a plugin of its own.
IDENTITY_RECORD = "stayfixed-overlay.toml"
# The overlay's commit-time secret scan, and the hook `pre-commit install` writes for it: `setup
# --overlay` installs the hook when it makes the overlay, and `doctor`'s `pre-commit` row asks
# whether it is there. The hook's *name* only: where it lives is `guards.hooks_dir`'s answer and
# never `.git/hooks`, because an overlay with `core.hooksPath` set -- a common global dotfiles
# setting -- or one that is a worktree or a submodule, where `.git` is a file, keeps its hooks
# somewhere else entirely. A hardcoded path would find the scan missing and warn in `doctor` with
# a remedy that cannot clear it. `docs/cli.md`'s
# `setup --git-hooks` section states the rule: `git rev-parse --git-path hooks`, never
# `core.hooksPath`.
PRE_COMMIT_CONFIG = ".pre-commit-config.yaml"
PRE_COMMIT_HOOK = "pre-commit"

# Every file `templates/overlay/` ships, in one fixed order. The list and the tree are two
# statements of one thing: `tests/overlay/test_template.py` asserts each way round, so a file
# deleted from the tree and a file added to it without a line here are both caught rather than
# one of them.
# The two files an overlay carries that can grant a capability, and the reason `overlay upgrade`
# has a decision list at all: an upgrade diffs these and asks about them "regardless of hash",
# because a hash match is not consent for a permission or a hook entry. Named once, unpacked
# into OVERLAY_FILES below, and published as CAPABILITY_FILES: one spelling, so a rename here is
# a rename everywhere, where a list derived by filtering OVERLAY_FILES against a second spelling
# of the two names would let the two drift apart.
CAPABILITY_NAMES = (f"{COMMON_CLAUDE}/permissions.json", f"{COMMON_CLAUDE}/hooks.json")

OVERLAY_FILES = (
    IDENTITY_RECORD,
    f"{COMMON_MEMORY}/_README.md",
    *CAPABILITY_NAMES,
    f"{COMMON_CODEX}/common.rules",
    f"{PROJECTS}/README.md",
    PRE_COMMIT_CONFIG,
    ".github/workflows/scan.yml",
    ".github/dependabot.yml",
    ".gitignore",
    "README.md",
)

CAPABILITY_FILES = CAPABILITY_NAMES

# The memory README an earlier release shipped, `_README.md` now: `memory.notes.walk` reads every
# `*.md` in a note store as a note and skips a name that starts with `_`. The files a release no
# longer ships are listed in `overlay.template`, beside the digests that say a copy of each is
# stayfixed's; this one is named here as well because it has a successor.
RETIRED_MEMORY_README = f"{COMMON_MEMORY}/README.md"
