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
Its line names the counts, the runner and the realpath of what ran, each inherited variable the
run did not get as it was (`removed from the run's environment: NODE_OPTIONS`), and the
configuration and
untracked files that can shape the report, twenty of each and a count of the rest, with a count of
the configuration files git ignores; `--json` carries the whole receipt, with every `NAME=value`
and `--option=value` value in the command replaced by `…`, and sends the runner's standard output
to standard error, so that standard output holds the one object. The runner's standard input is
`/dev/null`, so nothing piped into `prove` reaches the run; a test that reads it sees its end.
`proved` means the runner reported green on this tree, for the tests this command selected: the
code under test, any file in the runner's load path and the environment the runner reads can shape
its report.
The first runner adapter is pytest's: `pytest`, `py.test` and `python -m pytest`, also behind
`poetry run` or `uv run`, run as `<interpreter> -c <bootstrap>`, which runs pytest as `-m pytest`
would with the run directory never ahead of an installed module (last on the import path for
`python -m pytest`, so a project's own packages still import, and off it for the console script),
with a JUnit report of `prove`'s own, the project's `PYTHON*` variables kept, on any Python 3; it refuses `--junitxml`, `-p no:junitxml`, `-o junit_*`
and `-o addopts`, `--setup-plan`, `--setup-only` and `--collect-only` and their undashed
aliases, `--trace`, an `@file` word, the interpreter's `-O` (which compiles out the asserts
pytest does not rewrite), and an assigned `PYTEST_ADDOPTS`, `PYTEST_PLUGINS` or `PYTHONOPTIMIZE`,
and
names the configuration file `-c` names, wherever it lies, among the files that can shape the
report; `--pdb` is free, its debugger quitting at the end of standard input with the failure kept.
The jest, vitest and `node --test` adapters recognise `jest` and `vitest`, bare or after `npx`
(which is never run) or as `node [Node's flags] node_modules/jest/bin/jest.js` (the way to give
Node a flag, `--experimental-vm-modules` for jest's ES modules, since an inherited `NODE_OPTIONS`
is removed), and `node --test`; each runs the `node` on `PATH` with the entry point the
runner's own package names, found under `node_modules` from where the command runs up to the
project's top-level, and with a report of `prove`'s own (`entry-not-found` where there is none,
which names `prove --junit`; `npm test`, `yarn` and `pnpm` are recognised by none). They refuse the
options that move, replace or suppress the report, or that report a test passed that failed or never
ran: jest's `--json`, `--outputFile`, `--testResultsProcessor`, a `--config` given JSON text, `-u`
and `--collectTests`; vitest's `--outputFile`, `-u` (`--update=false` among them, `--update=new`
not), `--mergeReports` and `--dangerouslyIgnoreUnhandledErrors`; node's own reporters,
`--env-file`, its configuration file, `--test-update-snapshots` and `--test-rerun-failures`; and an
assigned `NODE_OPTIONS` (or, for `node --test`, `NODE_TEST_CONTEXT`). Each option
is read as the runner's own parser reads it; every other option is free, `-c`/`--config` naming a
file among them, and the file it names, like a file node's `--require` or `--import` names by its
path, is named among the files that can shape the report. A watch mode of any of the three never
ends, and is `not proven` (`never-ends`), read from its last setting as the runner reads it (jest's
`--watch --watchAll=false`, which ends, excepted: it is not proven either way). vitest's
subcommand in the command's first word is its own: `related` gets `--run`, `watch` and `dev` never
end, and `bench`, `list`, `init` and `doctor`, which run no test suite that reports, are
`not proven` (`no-test-run`).
The `go test` adapter runs the `go` on `PATH` as `go test -json`, counting only the events of its
standard output, with `GOENV=off`, `GOFLAGS=` and `GOTOOLCHAIN=local` set and an inherited `GOROOT`,
`GOOS` or `GOARCH` removed; it refuses `-exec`, `-toolexec`, `-overlay`, `-o`, `-c` and a false
`-json=`, read as the go command reads them (a build flag spelled `-test.` taking no value, and
nothing past a bare `-args`, `--args` or `--`), and an assigned `GOFLAGS`, `GOENV`, `GOTOOLCHAIN`,
`GOROOT`, `GOOS` or `GOARCH`.
`stayfixed prove --junit PATH -- COMMAND` counts the JUnit report of a runner no adapter knows,
read from the directory the command runs in, only where the run created or rewrote it as a regular
file (`junit-unchanged` otherwise); a command an adapter recognises is refused
(`junit-beside-adapter`), and every `--junit` receipt, one refused or not started too, marks the
runner not verified.
