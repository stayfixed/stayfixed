`stayfixed init --questions` asks ten questions instead of six, in the order the `init` skill walks
them: the name and the base branch, then the memory mode, the stack profile, CI, the commit
attribution check, the commit types, the files kept out of git, the coding agents and the
recommended plugins. `--json` gives each one four lines — what you get, what you give up, what it
leaves behind and how to undo it — and the skill offers to take every default before it asks
anything. Two answer flags are new on `init --yes`: `--attribution-check` and `--commit-type`.
`init --yes` ends with a `what I picked:` list naming the value it took for each question. The
recommended preset's commit types are now the Conventional Commits types (`feat`, `fix`, `build`,
`chore`, `ci`, `docs`, `perf`, `refactor`, `revert`, `style`, `test`) in place of a list that held
stayfixed's own `harden` and `guard`; a project that wants those sets `[commit_messages] types`.
