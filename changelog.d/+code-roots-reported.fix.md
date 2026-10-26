A `[ledger] code_roots` entry that no walk takes is no longer dropped without a word.
`stayfixed assess` has a `code-roots` probe that names each such entry with its reason: it names
the repository root itself (`.`), it leaves the repository or reaches its directory through a
link (`../shared`), or it names no directory here (a `lib` that does not exist), unless the
preset's default lists it (`src`, `tests`, `scripts`): a missing directory loses no walk. Nothing
is refused for it. `stayfixed test hygiene` no longer calls a tree clean when no entry is left to
walk: it says `no [ledger] code_roots entry names a directory here, so there was nothing to
check` instead.
