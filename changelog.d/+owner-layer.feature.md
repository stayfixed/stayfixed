The machine file (`~/.config/stayfixed/config.toml`) gains two tables of the owner's own:
`[guards]`, where `bg_cleanup = false` switches the `bg-cleanup` session guard off on that machine,
and `[budgets]`, which holds the four budgets that bound what a session loads
(`memory_index_words`, `startup_rules_words`, `volatile_notes_words`, `volatile_ttl_days`). A
repository's `stayfixed.toml` can set neither table's keys, and a gate's budget written in the
machine file is ignored with a note. `stayfixed setup` keeps both tables when it rewrites the file.
