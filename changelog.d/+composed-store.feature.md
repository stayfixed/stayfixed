`stayfixed attach` in `overlay` mode now composes one memory store for the harness under
`~/.local/share/stayfixed/stores/<id>/`, named by the binding id: a link to each of the overlay's
note groups for the project and one to its `MEMORY.md`. It points Claude Code at it with one key,
`autoMemoryDirectory`, written into the main checkout's git-ignored `.claude/settings.local.json`,
which every worktree reads, so the harness reads the overlay's notes from every worktree with
nothing placed per worktree and no approval to wait for. `--store` is no longer required: without
it, the store is the project's own directory in the overlay the machine records, and every remedy
stayfixed prints names plain `stayfixed attach`. A `[memory] mode = "overlay"` set only in the
overlay's project file applies on the first attach, and a re-attach once the mode is no longer
`overlay` takes the key and the store back, as `stayfixed detach` does. `detach` takes the key back
and removes the composed store's links and directory, keeping any note the harness wrote there. A
session whose composed store is gone hears one line naming it and `stayfixed attach` as the way
back. `attach` no longer takes the `autoMemoryDirectory` fallback it wrote when the harness memory
link could not be made; the pointer replaces it.
