A repository's `stayfixed.toml` may now carry `[guards]`: its `bg_cleanup = false` switches the
background-cleanup hint off by default for sessions in that repository, where it was ignored with a
note. The owner's layers still win: the overlay's `stayfixed.toml` files override it, and the
machine file's `[guards]` overrides both, so `bg_cleanup = true` there switches the hint back on.
A `[guards]` value that is not a switch is put back to the default, with a note, in a session, and
refused by a command, as any other key.
