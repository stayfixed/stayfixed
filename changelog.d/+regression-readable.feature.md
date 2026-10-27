A bug entry may carry `regression`, the argv that reproduces the bug, as an inline list of
double-quoted items: `regression: ["pytest", "-k", "total and not slow"]`. `stayfixed bugs check`
validates it, reporting a malformed list, an empty item or an item holding a control character
below U+0020, or DEL, as `unreadable-entry`. `stayfixed bugs renumber` leaves it exactly as written,
and names each entry whose `regression` still names the moved identifier, on its line and in
`--json`'s new `lists_naming_old`, since its sweep may have renamed the test such an argv selects.
`stayfixed bugs new` does not write one yet.
