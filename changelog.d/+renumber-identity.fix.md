`stayfixed bugs renumber` tells the files it must leave alone, the two it moves between, the index
and the entries, by the file and no longer by how the path is spelt. On a filesystem that folds
case, such as macOS's default, a ledger directory committed as `docs/Bugs` and configured as
`docs/bugs` made the sweep rewrite the `id:` of the void pointer it had just written, so
`stayfixed bugs check` then failed with `id-mismatch` and `duplicate-id`.
