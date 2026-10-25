An overlay is now named by its identity record, `stayfixed-overlay.toml` at its root, and no
longer by plugin manifests: the overlay template ships no `.claude-plugin/`, `.codex-plugin/` or
`hooks/hooks.json`, since `stayfixed attach` renders what the overlay holds into a plugin of its
own on each machine. `stayfixed setup --overlay` and `stayfixed overlay upgrade` refuse a tree
without the record, and no code migrates an existing overlay: add `stayfixed-overlay.toml` to its
root by hand, holding `owner = "<account>"`, `name = "<repository>"`, `requires = ">=0.1.0"` and
`layout = 1`, and move the floor your `.claude-plugin/plugin.json` declared under
`stayfixed.requires` into `requires`. The old manifests can then be deleted; nothing reads them.
If you published your own overlay template (`<account>/stayfixed-overlay-template`) with an earlier
release, add the record to it as well: `stayfixed setup --overlay create:` generates from it, and a
clone that carries no record is refused after GitHub has created the repository.
