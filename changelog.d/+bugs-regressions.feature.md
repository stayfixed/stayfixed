`stayfixed bugs regressions` runs the `regression` of every bug entry whose status is `fixed`, each
as `stayfixed prove` runs a command, from the project root with `[gates] custom_timeout_seconds` as
its bound, and prints one line for each entry with the receipt `prove` would print. It exits 0 when every
regression is proved and 1 when one is not, as `prove` does; after a Ctrl-C or a terminating signal
ended a run, nothing more starts. `--json` carries each entry's identifier, file, verdict and line,
and the runner's own output goes to standard error, so standard output stays one object. It runs
as a `[gates.custom]` gate, `run = ["stayfixed", "bugs", "regressions"]` where stayfixed is
installed, and in the reusable workflow as a `run` that installs the regressions' runner itself,
pinned, before `python3 -P -m stayfixed bugs regressions`; `docs/cli.md` spells both.
