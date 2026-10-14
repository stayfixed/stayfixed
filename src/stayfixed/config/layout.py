"""Where stayfixed's own files sit inside a project, derived once from `[paths]`.

`[paths] stayfixed` is the directory stayfixed's own project files go under, so that `uninstall`
can account for them and a reader can find them. The project's documents stay at their own
`[paths]` keys. Every other module asks this one for a derived location rather than spelling it.

A local run's default base is derived here too (`local_base`), because the three areas that
default one cannot import each other, and so is the `.gitignore` block both `init` and `attach`
write, with the attach ledger's path under it: the paths are the core's to name, and the core
may not import `attach`; the crossings still pinned are listed in
`tests/boundaries/test_delivery.py`.
"""

from __future__ import annotations

from stayfixed.config.schema import Config

# Where `attach` records what it added to a project, under the local state the ignore block keeps
# out of git. The core names the path and never reads the ledger: `uninstall` refuses an attached
# repository by the file's presence, and `doctor` reports on it.
ATTACH_LEDGER = ".stayfixed/local/attach.json"
# The `.gitignore` block `init` writes as a scaffold artifact and `attach` merges into the file,
# spelled once, or each would report the other's region as hand-edited. Its region name, the
# paths it keeps out of git — the local state, and the inventory `stayfixed assess` writes — and
# the note above them.
IGNORE_REGION = "ignore"
LOCAL_STATE_PATHS = (".stayfixed/local/", ".stayfixed/assessment.json")
IGNORE_NOTE = "# stayfixed's local state: yours, never a collaborator's."
IGNORE_BODY = "\n".join((IGNORE_NOTE, *LOCAL_STATE_PATHS))


def rules_file(config: Config, profile: str) -> str:
    """The project-relative path of a profile's rules.

    Only a location: `scaffold.engine.validate_sources` holds `profile` to `PROJECT_NAME`, and
    `contained()` decides whether the result may be written, as it does for every target.
    """
    return f"{config.paths.stayfixed}/rules/{profile}.md"


def local_base(config: Config) -> str:
    """The base a local run compares against when none is given: the remote-tracking ref of
    `[project] base_branch`, named in full.

    One spelling for every command that defaults one — `plan check`, `test attribute`,
    `assess`, `adopt promote` and `stayfixed gate` — because git resolves a short `origin/<b>`
    through `refs/tags/` first, so a tag of that spelling would stand in for the branch, and two
    spellings of one default would let a command and the gate it composes judge different
    commits. The loader holds the branch to `BRANCH_NAME`, so the name is one git can have.
    """
    return f"refs/remotes/origin/{config.project.base_branch}"
