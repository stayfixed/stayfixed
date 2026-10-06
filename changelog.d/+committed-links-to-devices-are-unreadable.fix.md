A committed bug-ledger entry, memory note or `MEMORY.md` that is a symbolic link to a device or a
pipe — `/dev/zero`, `/dev/stdin` — is now a file stayfixed cannot read, reported as each command
already reports one: an `unreadable-entry` finding from `stayfixed bugs check`, a quarantined note,
a store whose trust digest moves. So is a plan that `stayfixed plan check` finds outside a git
repository. Before, a link to `/dev/zero` made `bugs check`, `bugs index`, `bugs new` and
`gate --only bugs` read until memory ran out — in CI as anywhere else — and a link to `/dev/stdin`
or a FIFO made them, `memory refs`, `memory inventory`, `memory index --check`, `memory trust` and
`memory session-context` wait for input that never came. A link to a regular file is still read:
in overlay mode `stayfixed attach` links each memory group and `MEMORY.md` into the overlay, and
those read as they did.
`stayfixed attach` likewise stops, before anything is written, on a committed `.gitignore` that
links to a device or a pipe, as on one it cannot read; before, `/dev/zero` there read until memory
ran out and a FIFO waited for good.
