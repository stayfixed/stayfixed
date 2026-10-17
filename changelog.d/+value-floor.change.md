A session no longer stops on its configuration. The `bg-cleanup` guard now runs in every
repository, one with no `stayfixed.toml` included, on the preset and the machine owner's layer,
and only the machine file's `[guards] bg_cleanup = false` turns it off. A `stayfixed.toml` that does
not load, a symbolic link to one, or a broken machine file used to refuse every tool call the
agent made; now a tool call is refused only when a guard refuses it. A session reads the
`stayfixed.toml` it can: a section or key from a newer stayfixed is ignored and a value it cannot
use is put back to the preset's, so the project's other settings still apply. It drops the file
whole only when it cannot read it as TOML, or when a key has nothing to stand in for it, such as
an unusable `[project] name`, and then it names that key instead of calling it missing, or when
it is longer than 1 MiB or holds more settings it cannot use than its length allows (64 for a file
of up to 64 KiB, as few as 4 at 1 MiB), which read one by one would keep a hook past its
timeout. What the
session could not use is said once, when it starts, to you and to the agent, with
`stayfixed doctor` named for the detail; a tool call says nothing of it. `memory session-context`
reads the file the same way, so a key a newer release added no longer empties a session's notes,
and a machine file that does not load no longer ends it: the notes not kept in the overlay still
arrive.
