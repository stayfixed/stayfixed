Run from an agent's sandboxed shell, which cannot write stayfixed's machine directory or Claude
Code's user settings, `stayfixed setup`, `trust approve` and `trust revoke` now exit 2 with a
sentence saying a person must run them in their own terminal, outside the agent's sandbox, and
write nothing; `stayfixed memory index` still writes the index, leaves the store's approval as it
was, and says it could not be refreshed; and `stayfixed attach` finishes, its harness memory link
waiting for a new approval.
