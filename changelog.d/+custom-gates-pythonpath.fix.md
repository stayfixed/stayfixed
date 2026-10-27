The reusable workflow's step that runs a project's own gates now hands them an absolute
`PYTHONPATH`, so a `[gates.custom]` command can run `python3 -m stayfixed …` there and reach the
workflow's own stayfixed; with the relative path it had, such a command found no stayfixed.
