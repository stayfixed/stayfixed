"""The import surface: everything a consumer may import from this area.

A module and not the package's `__init__`, for the reason `stayfixed.docs.api`,
`stayfixed.ledger.api` and `stayfixed.memory.api` all give: area discovery imports a package
before it imports the submodule it wants, so a re-export list in `__init__.py` would pull this
whole area into every `discover()` call.

Six names, each with the consumer that reaches for it:

- `PROJECT_FILES`, for `scripts/check_artifacts.py`. It asks the built wheel whether the
  twelve shipped template files are actually in it, and before this list existed the only
  other way to ask was to spell twelve paths a second time in the script — which is the drift
  a published constant exists to stop.
- `project_templates` and the `Prepared` it returns, for `tests/project/test_fixture.py`,
  which plans both passes over a copy of the smoke fixture and asserts that the planning has
  nothing left to create, that every artifact the fixture's manifest records is one the plan
  recognises as already correct, and that every provenance it records is the one this build
  would write. Not that the fixture is what these templates render, which is what this line
  used to say: five of the fixture's files are its own — a bug index listing `BR-001`, a
  roadmap, its history, the trail, the runbook — and come back `skip_modified` with bytes that
  differ from the templates. That module's docstring states the measurement. A return type
  absent from this list is a value a consumer can hold and cannot declare, and
  `tests/test_surfaces.py` derives that rule rather than restating it.
- `rewrite_owned`, for `stayfixed adopt promote`, which moves `[stayfixed] state` and `enforced` as
  a project is adopted and its gates promoted. It is the one operation that rewrites a tool-owned
  key: a second copy in `adopt` would skip the `config` record's re-stamp, and `uninstall` would
  then keep every promoted project's `stayfixed.toml` as hand-edited.
- `CI_WORKFLOW`, for `stayfixed assess`'s workflow and code-owners probes, which must name
  stayfixed's own caller workflow and would otherwise spell it a third time beside `doctor`'s
  `WORKFLOW`.
- `ASSESSMENT`, for `stayfixed assess`, which writes the inventory `uninstall` takes back: one
  spelling of the path, so the file one writes is the file the other removes.

`read`, `fill` and `HARNESS_REGION` are **not** here: they are this area's own, reached by
`stayfixed.project.templates` and by nothing outside it. The branch grammar a rendered workflow
holds `[ci] gate_branch` to is `config.schema.BRANCH_NAME`, which the loader applies too. An area
that needs one grows this list deliberately, in a commit that says which area and why.
"""

from stayfixed.project.layout import PROJECT_FILES
from stayfixed.project.rewrite import rewrite_owned
from stayfixed.project.templates import CI_WORKFLOW, Prepared, project_templates
from stayfixed.project.uninstall import ASSESSMENT

__all__ = [
    "ASSESSMENT",
    "CI_WORKFLOW",
    "PROJECT_FILES",
    "Prepared",
    "project_templates",
    "rewrite_owned",
]
