Upgrading from 0.3.x changes four things without your acting. `stayfixed doctor` gains the
`approval-boundary` row, which is red, and `doctor` exits 1, on a machine whose
`~/.config/stayfixed/trust.json` holds an approval until the sandbox and the deny rule stand: run
`stayfixed setup --approval-boundary` and set `sandbox.enabled = true` as it says, or withdraw the
approval with `stayfixed trust revoke memory`. Its `codex-trust` row is now `codex-hooks`, so a
script reading `doctor --json` by row name reads the new name. The `bg-cleanup` session guard now
runs in every repository, one with no `stayfixed.toml` or already uninstalled included; only the
machine file's `[guards] bg_cleanup = false` switches it off. And `stayfixed setup` with neither
`--home` nor `--settings` writes Claude Code's user settings under the home the password database
records rather than under `HOME`. Every command that loads a project's configuration now refuses
a machine file whose `[guards]` or `[budgets]` it cannot use, as it refused an unusable
`[personal]`: a session reads past such a key, a command names the file and the key.
