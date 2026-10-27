Run from an agent's sandboxed shell, which cannot write stayfixed's machine directory or Claude
Code's user settings, `stayfixed setup` now exits 2 with a sentence saying a person must run it in
their own terminal, outside the agent's sandbox (or, met in their own terminal, that the directory
itself refuses writes), where it used to end as `internal error`; a run it stops part-way is
finished by the next.
