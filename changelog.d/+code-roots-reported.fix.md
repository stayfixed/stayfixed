A `[ledger] code_roots` entry that no walk takes is no longer dropped without a word.
`stayfixed assess` has a `code-roots` probe that names each such entry with its reason in
`.stayfixed/assessment.json`: it names the repository root itself (`.`), it is no readable path
inside the repository free of links, `..` and `.git` (`../shared`), or it names no directory here
(a `lib` that does not exist), unless the preset's default lists it (`src`, `tests`, `scripts`)
and another entry is walked: such a missing directory loses no walk. Nothing is refused for it. `stayfixed test hygiene` no longer
calls a tree clean when no entry is left to walk: after the uncommitted-change count, or
`no uncommitted change`, it says `no [ledger] code_roots entry names a directory here, so no code
root was walked`.
