Run from an agent's sandboxed shell, which cannot write stayfixed's machine directory or Claude
Code's user settings, `stayfixed setup` now exits 2 with a sentence saying a person must run it in
their own terminal, outside the agent's sandbox (or, met in their own terminal, that the directory
itself refuses writes), and writes nothing; the new `trust approve` and `trust revoke` do the same.
`stayfixed memory index` of an approved store, which in 0.3.1 failed on the trust record's
directory there, now writes the index, leaves the store's approval as it was and says it could not
be refreshed; an index that changes nothing in the store writes no record and so says nothing of
it. `stayfixed attach` finishes, says that the sandbox refused the refresh, and leaves its harness
memory link waiting for a new approval.
