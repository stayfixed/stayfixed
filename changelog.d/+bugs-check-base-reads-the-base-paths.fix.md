`stayfixed bugs check --base`, and the `bugs` gate under `stayfixed gate`, now read the base's
ledger where the base's own `stayfixed.toml` kept it. Before, they listed the base's entries at
the change's `[paths] bugs`, so a change that moved the ledger found no entries on the base and
could delete one in the same change and pass — under `stayfixed gate` whenever the base enforced
nothing, even in the run where the change enforced `bugs` itself. A base copy that does not load
now fails the check (exit 1), and one whose load meets a refusal, or whose `[ledger] id_prefix`
the ledger refuses, refuses (exit 2), rather than reading as a base with no ledger; a base with no
`stayfixed.toml` is still read at the change's paths. A change to `[ledger] id_prefix` now
answers for every entry under the old prefix, and a ledger deleted along with a `[paths]` move is
named at the paths the base kept it at.
