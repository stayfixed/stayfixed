`stayfixed attach` and `stayfixed detach`, run at a terminal with `HOME` unset by a user the
password database lists no home directory for, now refuse, saying that the database lists none and
that `HOME` set at a terminal names one, where they ended in an internal error ("Could not determine
home directory"). `stayfixed doctor`'s `harness-link` row, which sends such a user to
`stayfixed attach` for an overlay store, now says to run it from a terminal with `HOME` set.
