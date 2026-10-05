`stayfixed doctor` now names the machine configuration file it actually read when that file does
not load. Run from a terminal with `STAYFIXED_CONFIG` or `XDG_CONFIG_HOME` set and no `--machine`,
it read `~/.config/stayfixed/config.toml`, as it does whatever those variables say, and then told
the owner to fix the file the variable names instead, which it had not read.
