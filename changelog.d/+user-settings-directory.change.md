`stayfixed setup` with neither `--home` nor `--settings` now writes Claude Code's user settings
where `stayfixed doctor` reads them: `$CLAUDE_CONFIG_DIR/settings.json` when that variable is set
and standard input is a terminal, and `.claude/settings.json` under the home the password database
records otherwise, rather than always under `HOME`. A `CLAUDE_CONFIG_DIR` set with no terminal,
which a repository's committed `env` block can do for an agent's shell, is passed over, and the
report says so and names the file written.
