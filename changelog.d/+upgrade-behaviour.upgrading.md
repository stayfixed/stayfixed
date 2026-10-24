Upgrading from 0.3.x changes two things without your acting. `stayfixed doctor`'s `codex-trust`
row is gone, so a script reading `doctor --json` by row name finds no row of that name. And the
`bg-cleanup` session guard now runs in every repository, one with no `stayfixed.toml` or already
uninstalled included, unless a `[guards] bg_cleanup = false` switches it off: the machine file's,
the overlay's, or the repository's, in that order of precedence.
