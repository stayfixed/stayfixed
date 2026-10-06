Every integer in `stayfixed.toml` — a `[budgets]` value, `[gates] custom_timeout_seconds` —
must now be below 2,147,483,648, and one at or past that is refused as
the configuration's own error, "must be a positive integer below 2,147,483,648", naming the key
and never the value. A hexadecimal, octal or binary literal converts at any length, and a decimal
of a few hundred digits is inside Python's limit, so such a number used to reach
`custom_timeout_seconds`' reader and end `stayfixed assess` and `stayfixed gate` in an internal
error.
A hexadecimal, octal or binary integer, which TOML reads at any length, no longer ends a command in
an internal error where its decimal spelling would pass 4,300 digits: `stayfixed init` adopting a
`stayfixed.toml` that holds one now refuses it as the configuration's own error, `[stayfixed]
preset` holding one is refused as a name that is not a preset's, and `stayfixed assess` reads one
in a profile's `pyproject.toml` as a value it cannot read.
