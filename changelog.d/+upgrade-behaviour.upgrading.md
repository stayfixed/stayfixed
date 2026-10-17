Upgrading from 0.3.x changes two things without your acting. `stayfixed doctor`'s `codex-trust`
row is now `codex-hooks`, so a script reading `doctor --json` by row name reads the new name. And
the `bg-cleanup` session guard now runs in every repository, one with no `stayfixed.toml` or
already uninstalled included; only the machine file's `[guards] bg_cleanup = false` switches it
off.
