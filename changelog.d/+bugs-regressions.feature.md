`stayfixed bugs regressions` runs the `regression` of every bug entry whose status is `fixed`, each
as `stayfixed prove` runs a command, from the project root with `[gates] custom_timeout_seconds` as
its bound, and prints one line an entry with the receipt `prove` would print. It exits 0 when every
regression is proved, 1 when one is not, and 130 when a Ctrl-C or a terminating signal ended a run,
after which nothing more starts. `--json` carries each entry's identifier, file, verdict and line,
and the runner's own output goes to standard error, so standard output stays one object.
