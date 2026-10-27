Upgrading from 0.3.x changes these without your acting:

- `stayfixed doctor`'s `codex-trust` and `harness-link` rows are gone, and `store-debris` is now
  the `memory` row, so a script reading `doctor --json` by row name finds no row of the old names.
- `stayfixed doctor` exits `0` where 0.3.1 exited `1` for a repository with no `stayfixed.toml`, a
  `stayfixed.toml` a newer stayfixed wrote, and a hook entry claiming the stayfixed marker in a
  file stayfixed does not write: each is now a warning, not red.
- The `bg-cleanup` session guard now runs in every repository, one with no `stayfixed.toml` or
  already uninstalled included, unless a `[guards] bg_cleanup = false` switches it off: the machine
  file's, the overlay's, or the repository's, in that order of precedence.
