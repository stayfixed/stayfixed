`stayfixed attach` and `detach` changed what a script can rely on, each described in its entry
below:

- `attach` attaches a repository whose `memory.mode` is not `overlay`, where 0.3.1 refused it with
  exit `2`.
- `attach` and `attach --check` refuse a `.claude` that is a symlink on every run, where 0.3.1
  refused it only when something was granted; and a path `attach` places that the repository
  tracks, or that a `.gitignore` re-includes with `!`, where 0.3.1 attached it.
- `attach` merges no hook entry into `.claude/settings.local.json`; the overlay's hooks arrive in
  the rendered plugin, and the entries an earlier release merged there are taken back.
  `attach --check` and `--json` no longer carry `added_hooks`.
- `attach` writes nothing into `.gitignore`, and `detach --json` no longer carries
  `ignore_region_removed`: a `stayfixed:ignore` region an earlier `attach` wrote stays until you
  remove it.
