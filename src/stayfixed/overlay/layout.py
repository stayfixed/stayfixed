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
COMMON_RULES = f"{COMMON}/rules"
COMMON_MEMORY = f"{COMMON}/memory"
COMMON_CLAUDE = f"{COMMON}/claude"
COMMON_CODEX = f"{COMMON}/codex"
PLUGIN_MANIFEST = ".claude-plugin/plugin.json"
MARKETPLACE_MANIFEST = ".claude-plugin/marketplace.json"
# The Codex half of `PLUGIN_MANIFEST`, named here rather than spelled as a literal inside
# `OVERLAY_FILES`: `overlay init` has to suffix it for the same reason it suffixes the other
# two — a harness installs a plugin by the name in its manifest, and this project ships a Codex
# half of everything else.
CODEX_PLUGIN_MANIFEST = ".codex-plugin/plugin.json"

# Every file `templates/overlay/` ships, in one fixed order. The list and the tree are two
# statements of one thing: `tests/overlay/test_template.py` asserts each way round, so a file
# deleted from the tree and a file added to it without a line here are both caught rather than
# one of them.
# The two files an overlay carries that can grant a capability, and the reason `overlay upgrade`
# has a decision list at all: an upgrade diffs these and asks about them "regardless of hash",
# because a hash match is not consent for a permission or a hook entry. Named once, unpacked
# into OVERLAY_FILES below, and published as CAPABILITY_FILES: one spelling, so a rename here is
# a rename everywhere. The list used to be derived by filtering OVERLAY_FILES against a second
# spelling of the two names, under a comment claiming they were not spelled twice.
CAPABILITY_NAMES = (f"{COMMON_CLAUDE}/permissions.json", f"{COMMON_CLAUDE}/hooks.json")

# A directory's own documentation rather than a file in its own right: `overlay create`
# drops one of these into each directory the owner fills, and the template README describes
# those as directories on purpose. `tests/overlay/test_template.py` accounts for the tree
# by this rule; a third such directory needs no edit there. The root `README.md` is not a
# placeholder — the rule applies to a basename BELOW a directory, never to the root.
#
# `_README.md` is the spelling for a directory the note reader walks: `memory.notes.walk` reads
# every `*.md` in a note store as a note and skips a name that starts with `_`, so a `README.md`
# there is a note with no frontmatter and `memory index --check` fails on it in every project
# attached to the overlay. `common/memory/` is that directory.
PLACEHOLDER_NAMES = ("README.md", "_README.md")

OVERLAY_FILES = (
    PLUGIN_MANIFEST,
    MARKETPLACE_MANIFEST,
    CODEX_PLUGIN_MANIFEST,
    "hooks/hooks.json",
    f"{COMMON_MEMORY}/_README.md",
    *CAPABILITY_NAMES,
    f"{COMMON_CODEX}/common.rules",
    f"{PROJECTS}/README.md",
    ".pre-commit-config.yaml",
    ".github/workflows/scan.yml",
    ".github/dependabot.yml",
    ".gitignore",
    "README.md",
)

CAPABILITY_FILES = CAPABILITY_NAMES

# Files an earlier release shipped and this one does not, which `overlay upgrade` removes where
# they still hold what stayfixed wrote (`overlay.template.retired`). `common/memory/README.md` is
# `_README.md` now, for the reason `PLACEHOLDER_NAMES` gives. The template's own `attach` skill was
# a subset of the plugin's, which also covers detaching and a moved remote, and `common/rules/` was
# a directory nothing read. None of them is ever a member of `OVERLAY_FILES`:
# `tests/overlay/test_template.py` holds that.
RETIRED_MEMORY_README = f"{COMMON_MEMORY}/README.md"
RETIRED_ATTACH_SKILL = "skills/attach/SKILL.md"
RETIRED_RULES_README = f"{COMMON_RULES}/README.md"
RETIRED_OVERLAY_FILES = (RETIRED_MEMORY_README, RETIRED_ATTACH_SKILL, RETIRED_RULES_README)
# The shipped file that took each retired one's place, which `overlay init` writes when it removes
# the old name and the new one is not there (`overlay.create._retire` says why).
SUCCESSORS = {RETIRED_MEMORY_README: f"{COMMON_MEMORY}/_README.md"}
