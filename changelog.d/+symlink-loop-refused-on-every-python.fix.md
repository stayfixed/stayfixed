On Python 3.11 and 3.12, `stayfixed setup` given a symbolic-link loop at `~/.claude`, `--home`,
`--root`, `--settings` or `--overlay` ended in `internal error: RuntimeError`, and
`stayfixed setup --git-hooks` did at `--root`. Each is now refused (exit `2`) naming the path and
saying it loops, before anything is written, and the same on every Python: 3.13 had refused most of
them in other words and recorded an overlay past a looping `--root`.
