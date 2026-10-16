`stayfixed setup` with neither `--home` nor `--settings` now writes Claude Code's user settings
under the home the password database records, where `stayfixed doctor` reads them, rather than
under `HOME`. Where `CLAUDE_CONFIG_DIR` names another settings directory that exists outside the
project, its `settings.json` takes the same rules too, recorded under that directory in
`[setup] added_rules_in` so that `[setup] ask_rules = false` takes them back there as well; any
other such directory is named and left alone.
