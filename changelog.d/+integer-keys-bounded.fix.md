Every integer in `stayfixed.toml` — a `[budgets]` value, `[gates] custom_timeout_seconds` — must
now be below 2,147,483,648, and one at or past that is refused as the configuration's own error,
"must be a positive integer below 2,147,483,648", naming the key and never the value. TOML reads a
hexadecimal, octal or binary integer at any length, and a decimal of a few hundred digits is inside
Python's limit, so such a number used to reach `custom_timeout_seconds`' reader and end
`stayfixed assess` and `stayfixed gate` in an internal error. Where an integer's decimal spelling
would pass 4,300 digits, these no longer end in an internal error either: `stayfixed init`
adopting a `stayfixed.toml` that holds one refuses it as the configuration's own error,
`[stayfixed] preset` holding one is refused as a name that is not a preset's, `stayfixed assess`
reads one in a profile's `pyproject.toml` as a value it cannot read, and `stayfixed setup` keeps
one you wrote in the machine configuration file, writing it back in hexadecimal.
