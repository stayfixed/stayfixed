"""Where stayfixed's own files sit inside a project, derived once from `[paths]`.

`[paths] stayfixed` is the directory stayfixed's own project files go under, so that `uninstall`
can account for them and a reader can find them. The project's documents stay at their own
`[paths]` keys. Every other module asks this one for a derived location rather than spelling it.

A local run's default base is derived here too (`local_base`), because the three areas that
default one cannot import each other.
"""

from __future__ import annotations

from stayfixed.config.schema import Config


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
