`stayfixed prove -- COMMAND` runs a test command in the directory it is typed in and answers from
what the test runner itself reported, never from what the command printed: `proved` (0), `failed`
(1) for a failed test, a run of no test or one that skipped every test, `not proven` (1) for a
command no runner adapter recognises, a run that wrote no report or one that does not read, a run
interrupted or past `--timeout` (an hour by default), or a green report from a command that exited
non-zero, and `refused` (2) for a command its runner's adapter refuses (an option that moves,
replaces or suppresses the report), one that assigns a variable its runner reads to shape the
report, wherever it spells the assignment, before `uv run` or after it, one that gives `uv` an
option that loads an environment or configuration file (`--env-file`, `--config-file`) or assigns
`UV_ENV_FILE` or `UV_CONFIG_FILE`, and a program that changed between the plan and the launch
(`resolved-elsewhere`). It needs no `stayfixed.toml` and takes neither `--root` nor `--machine`.
Its line names the counts, the runner and the realpath of what ran, and the configuration and
untracked files that can shape the report, twenty of each and a count of the rest, with a count of
the configuration files git ignores; `--json` carries the whole receipt, with every `NAME=value`
and `--option=value` value in the command replaced by `…`, and sends the runner's standard output
to standard error, so that standard output holds the one object. `proved` means the runner reported
green on this tree, for the tests this command selected: the code under test, any file in the
runner's load path and the environment the runner reads can shape its report.
