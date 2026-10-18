A bug entry may carry `regression`, the argv that reproduces the bug, as an inline list of
double-quoted items: `regression: ["pytest", "-k", "total and not slow"]`. `stayfixed bugs check`
validates it, reporting a malformed list, an empty item or an item holding a control character as
`unreadable-entry`, and `stayfixed bugs renumber` never rewrites it. `stayfixed bugs new` does not
write one yet, and every other byte the ledger writes and prints is unchanged.
