`stayfixed attach` and `attach --check` now refuse, before anything is written, a `[project] name`
or a `memory.groups` entry longer than a file name may be (255 bytes on common filesystems) when
the overlay has no directory for the project yet — including an overlay with no `projects/` at
all. `--check` used to report nothing wrong, and `attach` wrote `.git/info/exclude`, `.gitignore`
and its ledger before failing with an internal error ("File name too long") that printed the
name. The refusal names neither the project nor the group.
