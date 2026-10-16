`stayfixed setup` with neither `--home` nor `--settings` now writes Claude Code's user settings
under the home the password database records, where `stayfixed doctor` reads them, rather than
under `HOME`. Where `CLAUDE_CONFIG_DIR` names another settings directory, setup does not write
there and names it for you to copy the rules into: a repository's `env` block, direnv or mise can
set that variable, and it may name another program's `settings.json`.
