`stayfixed prove -- COMMAND` runs a test command as typed and says what its runner's own report
proves: `proved` (exit 0), `failed` or `not proven` (1), or `refused` (2). Text the command prints
is never counted, and a run of no test, or of skipped tests alone, fails. Adapters ship for
pytest, jest, vitest, `node --test` and `go test`, each adding only its report options; each
refuses the options under which a runner's green report covers tests that never ran or checked
nothing (pytest's `--setup-plan`, the interpreter's `-O`, a snapshot rewrite, and the like) and
says `not proven` for a watch mode. `--junit PATH` counts the JUnit report of any other runner,
and its receipt says the runner was not verified. The receipt names the realpath of what ran and
the untracked test files in the runner's discovery set, and `--json` prints it whole; a `--json`
after the `--` is the command's own and is handed to it. `docs/cli.md`, the `stayfixed prove`
section, has every rule.
