`stayfixed docs trail` and its `--check` now name a `trail.toml` they cannot read, parse or accept
by its path in the project (`docs/trail.toml`), as every other message of `stayfixed docs` names a
file, instead of by the absolute path it was opened from on this machine.
