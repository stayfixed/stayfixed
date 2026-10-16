The machine file (`~/.config/stayfixed/config.toml`) gains two tables of the owner's own:
`[guards]`, where `bg_cleanup = false` switches the `bg-cleanup` session guard off on that machine,
and `[budgets]`, which holds the four budgets that bound what a session loads
(`memory_index_words`, `startup_rules_words`, `volatile_notes_words`, `volatile_ttl_days`). A
repository's `stayfixed.toml` can set neither table's keys. Every command that loads the
project's configuration reads both tables as a session does, so `memory fit`, `memory index` and
`memory inventory` measure the budgets a session runs on, and refuses an unknown key, an unusable
value or a gate's budget there, naming the file and the key; a session ignores a gate's budget, or
any such key, with a note. `stayfixed setup` keeps both tables when it rewrites the file.
