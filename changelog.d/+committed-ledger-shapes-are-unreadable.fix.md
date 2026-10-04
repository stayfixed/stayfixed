A `.stayfixed/local/attach.json` in a shape `stayfixed attach` never writes is now read as a ledger
that cannot be read, rather than failing with an internal error: a `store` holding a NUL character,
a list field such as `allow` or `rules` holding something other than a list, and JSON nested deeper
than the parser follows. `stayfixed doctor`'s `attached` and `hook-entries` rows name the file as
one that cannot be read instead of reading red, "this check could not run", and `stayfixed attach`
and `stayfixed detach` say the file is not a ledger. A settings file nested that deeply is likewise
one `hook-entries` reports it could not read, and one `stayfixed attach` refuses to merge into.
On Python 3.11 and 3.12, a ledger `store` or a note's backticked path that runs through a symbolic
link loop no longer ends `stayfixed doctor` in the same red row or `stayfixed memory refs` in an
internal error: the store is not this project's, and the path is reported as one that does not
resolve.
