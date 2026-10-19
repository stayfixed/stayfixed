`stayfixed setup --settings` is gone: `setup` now writes `~/.claude/settings.json` through the
links a dotfiles manager makes, so the file a link leads to gets the rules. A script that passed
`--settings` must drop the flag. If you kept stayfixed's `config.toml` or `trust.json` under the
password database's home while `HOME` named another directory, move them under `HOME`'s
`.config/stayfixed`.
