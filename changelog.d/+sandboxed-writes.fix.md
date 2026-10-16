Run from an agent's sandboxed shell, which cannot write stayfixed's machine directory or Claude
Code's user settings, `stayfixed setup`, `trust approve` and `trust revoke` now exit 2 with a
sentence saying a person must run them in their own terminal, outside the agent's sandbox (or,
met in their own terminal, that the directory itself refuses writes), and write nothing;
`stayfixed memory index` still writes the index, leaves the store's approval as it was, and says
it could not be refreshed; and `stayfixed attach` finishes, says the refresh was refused, and
leaves its harness memory link waiting for a new approval.
