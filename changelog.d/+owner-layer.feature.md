The machine file (`~/.config/stayfixed/config.toml`) gains two tables of the owner's own:
`[guards]`, where `bg_cleanup = false` switches the `bg-cleanup` session guard off on that machine,
and `[budgets]`, which holds the four budgets that bound what a session loads
(`memory_index_words`, `startup_rules_words`, `volatile_notes_words`, `volatile_ttl_days`). A
repository's `stayfixed.toml` may set a `[guards]` default and the same four budgets; the overlay's
`stayfixed.toml` files override the repository's, and the machine file's win over both, so
`bg_cleanup = true` there switches the guard back on. Every command that loads the
project's configuration reads both tables as a session does, so `memory fit`, `memory index` and
`memory inventory` measure the budgets a session runs on. An unknown key, an unusable value or a
gate's budget there costs that key alone and is said, by a command on stderr and by a session
when it starts, never refused, so a key a later release writes stops no older command; only a
machine file that does not load is refused by a command. `stayfixed setup` keeps both tables when
it rewrites the file.
