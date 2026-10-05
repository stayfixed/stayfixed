`stayfixed attach` and `attach --check` now refuse, before anything is written, a project whose
directory in the overlay would hold a path longer than the system allows: its binding record, its
notes index, or the directory of one of its `memory.groups`. A long `[project] name` or a long
`memory.groups` entry could leave the project's directory itself within the limit while one of
those paths was past it; `--check` then reported nothing wrong, and `attach` wrote `.gitignore`,
the settings merge, its ledger and the binding record before failing with an internal error
("File name too long") while linking the notes. The refusal names neither the project nor a group.
