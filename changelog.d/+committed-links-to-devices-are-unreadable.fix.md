A committed file stayfixed reads that is a symbolic link to a device or a pipe — `/dev/zero`,
`/dev/stdin`, a FIFO — is now a file stayfixed cannot read, reported as each command already
reports one. Before, a link to `/dev/zero` read until memory ran out, in CI as anywhere else, and a
link to `/dev/stdin` or a FIFO waited for input that never came:

- a bug-ledger entry: an `unreadable-entry` finding from `stayfixed bugs check`, where `bugs check`,
  `bugs index`, `bugs new` and `gate --only bugs` read or waited for good;
- a memory note or `MEMORY.md`: a quarantined note, or a store whose trust digest moves, where
  `memory refs`, `memory inventory`, `memory index --check`, `memory trust` and `memory
  session-context` waited;
- a plan that `stayfixed plan check` finds outside a git repository;
- `.claude/settings.local.json`: `stayfixed attach`, `attach --check` and `stayfixed detach` fail
  (exit `1`), "cannot be read: not a regular file", before anything is written or removed;
- `.stayfixed/local/attach.json`: `stayfixed detach` fails (exit `1`) the same way, and `attach`
  refuses a ledger that is a link at all, as before;
- `.gitignore`: `stayfixed attach` refuses it (exit `2`) when it needs to add its region there.

A link to a regular file is still read: in overlay mode `stayfixed attach` links each memory group
and `MEMORY.md` into the overlay, and those read as they did. The trust digest reads a note or
`MEMORY.md` up to 64 MiB, so a change to one longer than that moves the store's digest only where it
falls inside its first 64 MiB. `attach` and `detach` name each of these files as the project does,
in this refusal and in the one for such a file that is not UTF-8, rather than by its absolute path
on this machine. Every one of these files is also read only up to 64 MiB, and a longer one is a
file stayfixed cannot read, met as each command above meets one, because some regular files never
end.
