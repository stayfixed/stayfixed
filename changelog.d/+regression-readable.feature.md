A bug entry may carry `regression`, the argv that reproduces the bug, as an inline list of
double-quoted items: `regression: ["pytest", "-k", "total and not slow"]`. `stayfixed bugs check`
validates it, reporting a malformed list, an empty item or an item holding a control character
below U+0020, or DEL, as `unreadable-entry`, and `stayfixed bugs renumber` leaves it exactly as
written. `stayfixed bugs new` does not write one yet, and every other byte the ledger writes and
prints is unchanged but one: a refusal of an unsupported escape in any frontmatter value, such as
`\<ESC>` in a `title`, now prints a character that does not print, an ESC or a line break, escaped
rather than raw.
