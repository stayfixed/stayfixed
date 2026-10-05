Upgrading from 0.2.0, in one place: what a script, a CI step or a habit may rely on that is gone or
has moved. `stayfixed adopt begin` is gone, because `stayfixed adopt promote` moves a project out of
`initialised` itself, and a project 0.2.0 left in `adopting` keeps working; so is `stayfixed test
audit-entrypoints`, which no gate ran; and so is the `stayfixed release` group (`check`, `notes`,
`hashes`), which only ever checked stayfixed's own release. `stayfixed docs check` has lost
`--memory-graph`, whose link graph `stayfixed memory refs` now reports, and `--store` with it. Two
session-start bundles are gone, `preset-rules` and `index`: `stayfixed memory session-context
--bundle` refuses either with exit `2`, and `memory fit --json` no longer lists them. `stayfixed
doctor` reports the same sixteen checks in a new order, the installation's own eleven first, so a
script that read the report by position should match on each check's name. `stayfixed test hygiene
--json` moves its counts under `profiles`, by profile name. And `stayfixed overlay upgrade` and
`overlay init` remove two files the overlay template no longer ships, its copy of the `attach` skill
and `common/rules/README.md`, keeping and naming a copy you edited. Each of these has its own entry
in these notes, with the detail.
