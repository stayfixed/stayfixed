A `.stayfixed/local/attach.json` in a shape `stayfixed attach` never writes is now read as a ledger
that cannot be read, rather than failing with an internal error: a `store` holding a NUL character,
a list field such as `allow` or `rules` holding something other than a list, JSON nested deeper
than the parser follows, and JSON holding a number longer than Python converts to an integer (4,300
digits by default). `stayfixed doctor`'s `attached` and `hook-entries` rows name the file as
one that cannot be read instead of reading red, "this check could not run", and `stayfixed attach`
and `stayfixed detach` say the file is not a ledger. A settings file nested that deeply, or holding
such a number, is likewise one `hook-entries` reports it could not read, and one `stayfixed attach`
refuses to merge into. A line of that kind in the hook sink's log no longer turns `stayfixed
doctor`'s `diagnostics` row red either: it is not counted as a recorded failure.
On Python 3.11 and 3.12, a ledger `store` or a note's backticked path that runs through a symbolic
link loop no longer ends `stayfixed doctor` in the same red row or `stayfixed memory refs` in an
internal error: the store is not this project's, and the path is reported as one that does not
resolve.
