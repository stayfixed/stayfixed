Every `stayfixed prove` and `stayfixed gate` run now leaves one evidence record on the machine: a
JSON line in `$XDG_STATE_HOME/stayfixed/evidence/<key>.jsonl` where `XDG_STATE_HOME` is an absolute
path, else in `~/.local/state/stayfixed/evidence/<key>.jsonl`, one file per project, keyed by the
repository's `origin` (normalised, so every clone of one repository shares it) or else by the real
path of its top-level. A `prove` line carries the run's receipt, the realpath of what ran and, where
one is named, the runner's entry; a `gate` line carries its mode, its flags, the commit and each
gate's verdict word. A record is a log that nothing reads: it is never written inside a git
checkout unless that checkout ignores it (so a dotfiles repository at the home that ignores
`.local/state` gets its records), and one that cannot be written is a warning on standard error
that changes neither the verdict nor the exit code.
The reusable workflow gains two inputs, `evidence` (off by default) and `evidence-retention-days`
(14): with `evidence: true`, a last step uploads the job's evidence records as an artifact named
for `only:` and the attempt, after both gate steps whatever they came to; the upload may fail
without failing the job, and it runs no command and reads no secret.
