`stayfixed bugs new` and `stayfixed bugs index` no longer end in `internal error` (exit `2`)
when the index cannot be written, for example in a directory this user cannot write. `bugs new`
writes the entry before the index, so its failure left a filed entry behind a line that did not
say so, and running the command again filed the same report twice. It now exits `1` with
`filed <entry>, but <index> could not be written (<reason>); once it can be, run `stayfixed bugs
index`, not this command again, which would file it a second time`. `bugs index` exits `1` with
the reason too.
