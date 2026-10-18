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
to standard error, so that standard output holds the one object. The runner's standard input is
`/dev/null`, so nothing piped into `prove` reaches the run; a test that reads it sees its end.
`proved` means the runner reported green on this tree, for the tests this command selected: the
code under test, any file in the runner's load path and the environment the runner reads can shape
its report.
The first runner adapter is pytest's: `pytest`, `py.test` and `python -m pytest`, also behind
`poetry run` or `uv run`, run as `<interpreter> -P -m pytest` with a JUnit report of `prove`'s own,
the project's `PYTHON*` variables kept; it refuses `--junitxml`, `-p no:junitxml`, `-o junit_*`
and `-o addopts`, `--setup-plan`, `--setup-only` and `--collect-only` and their undashed
aliases, `--trace`, an `@file` word, and an assigned `PYTEST_ADDOPTS` or `PYTEST_PLUGINS`, and
names the configuration file `-c` names, wherever it lies, among the files that can shape the
report; `--pdb` is free, its debugger quitting at the end of standard input with the failure kept.
The jest, vitest and `node --test` adapters recognise `jest` and `vitest`, bare or after `npx`
(which is never run), and `node --test`; each runs the `node` on `PATH` with the entry point the
runner's own package names, found under `node_modules` from where the command runs up to the
project's top-level, and with a report of `prove`'s own (`entry-not-found` where there is none,
which names `prove --junit`; `npm test`, `yarn` and `pnpm` are recognised by none). They refuse the
options that move, replace or suppress the report, or that report a test passed that failed or never
ran: jest's `--json`, `--outputFile`, `--testResultsProcessor`, a `--config` given JSON text, `-u`,
`--no-ci`, `--collectTests` and watch modes; vitest's `--outputFile`, `-u` (`--update=false` among
them), `--mergeReports`, `--dangerouslyIgnoreUnhandledErrors` and `--watch`; node's own reporters,
`--env-file`, its configuration file, `--test-update-snapshots`, `--test-rerun-failures` and
`--watch`; and an assigned `NODE_OPTIONS` (or, for `node --test`, `NODE_TEST_CONTEXT`). Each option
is read as the runner's own parser reads it; every other option is free, `-c`/`--config` naming a
file among them, and the file it names, like a file node's `--require` or `--import` names by its
path, is named among the files that can shape the report.
`stayfixed prove --junit PATH -- COMMAND` counts the JUnit report of a runner no adapter knows,
read from the directory the command runs in, only where the run created or rewrote it as a regular
file (`junit-unchanged` otherwise); a command an adapter recognises is refused
(`junit-beside-adapter`), and every `--junit` receipt, one refused or not started too, marks the
runner not verified.
