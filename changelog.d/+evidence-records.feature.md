Every `stayfixed prove` and `stayfixed gate` run now leaves one evidence record on the machine: a
JSON line in `~/.local/state/stayfixed/evidence/<key>.jsonl`, the home being the password
database's (no `HOME` or `XDG_STATE_HOME` moves it), one file per project, keyed by the
repository's `origin` (normalised, so every clone of one repository shares it) or else by the real
path of its top-level. A `prove` line carries the run's receipt, the realpath of what ran and, where
it is `node` running jest's or vitest's entry, that entry's too; a `gate` line carries its mode,
its flags, the commit and each gate's verdict word. A record is a log that nothing reads: it is
never written inside a repository, and one that cannot be written is a warning on standard error
that changes neither the verdict nor the exit code.
