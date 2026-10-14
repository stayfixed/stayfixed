`[ledger] evidence_boundary_required_for` is now checked against the bug ledger's severities
(`high`, `medium`, `low`). A value naming none of them — `"critical"`, `"High"`, a misspelling —
used to load and require the evidence line of no entry, so every `high` entry passed `stayfixed
bugs check` without one. Such a configuration, accepted until now, is refused (exit 2) by every
command that reads the ledger, `stayfixed bugs`, `plan check`, `memory refs`, `init` and
`upgrade` among them, with a message that counts the values and does not quote them;
`stayfixed uninstall` still runs.
