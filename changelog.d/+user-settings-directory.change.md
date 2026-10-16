`stayfixed setup` with neither `--home` nor `--settings` now writes Claude Code's user settings
under the home the password database records, where `stayfixed doctor` reads them, rather than
under `HOME`, and reads an existing file past a leading byte-order mark, as Claude Code does,
keeping the mark. Where `CLAUDE_CONFIG_DIR` names another settings directory that exists under that
home and outside the project and every other checkout of its repository, its `settings.json` takes
the same rules too, recorded under that directory, by its absolute path, in
`[setup] added_rules_in` so that `[setup] ask_rules = false` takes them back there as well, and
takes back nothing but those; any other such directory, and any at all on a run given `--home` or
`--settings`, is named and left alone, and one under neither the home nor the project is not even
looked at. The report says "deny rules merged" only when it added a deny rule.
