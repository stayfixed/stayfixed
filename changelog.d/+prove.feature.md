`stayfixed prove -- COMMAND` runs a test command as typed and says what its runner's own report
proves: `proved` (exit 0), `failed` or `not proven` (1), or `refused` (2). Text the command prints
is never counted, and a run of no test, or of skipped tests alone, fails. Adapters ship for
pytest, jest, vitest, `node --test` and `go test`, each adding only its report options; each
refuses only the options under which a runner reports tests that never ran as passed (pytest's
`--setup-plan`, a snapshot rewrite, and the like) and says `not proven` for a watch mode.
`--junit PATH` counts the JUnit report of any other runner. The receipt names the realpath of
what ran and the untracked test files in the runner's discovery set, and `--json` prints it whole. `docs/cli.md`, the
`stayfixed prove` section, has every rule.
