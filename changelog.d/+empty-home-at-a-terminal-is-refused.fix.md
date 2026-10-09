At a terminal where `HOME` is set and empty, `stayfixed attach` and `stayfixed detach` now refuse
(exit `2`) and `stayfixed setup` fails (exit `1`) before writing anything, saying that `HOME` names
no home directory. Python reads an empty `HOME` as the root directory, so `attach` with an approved
store ended in an internal error making the harness memory link, through which Claude Code reads
the project's notes, under `/.claude`, and `setup` ended in an internal error creating
`/.config`, or, given `--machine`, wrote that file and then refused (exit `2`) to write
`/.claude/settings.json`. `stayfixed doctor`'s `attached` row there now
says that `HOME` names no home directory, where it checked a path under `/.claude` and sent you to
the `attach` that failed.
