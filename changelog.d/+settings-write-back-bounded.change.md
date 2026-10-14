`stayfixed attach`, `attach --check` and `stayfixed detach` now refuse, before anything is written,
a `.claude/settings.local.json` that stayfixed's indented write-back would make longer than the
64 MiB it reads: "would be longer than this reader reads once written back". Written back
indented, a short document many levels deep grows by its depth on every line, so a 12 KB file 6,000
lists deep came back from 0.2.0's `attach` as 72 MB, past what this release reads. `attach` and
`--check` refuse such a file (exit `2`) even when the run would not rewrite it. Every other JSON
document stayfixed writes back indented — a settings file `init`, `upgrade` or `setup` rewrites, an
overlay manifest `overlay init` renames — is stopped the same way before it is written, so no
command leaves behind a file its next read cannot take: `stayfixed setup` and `overlay init` fail
(exit `1`) naming the file. That includes a `~/.claude/settings.json` 0.2.0's own `setup` already
wrote back past 64 MiB, which has to be cut down by hand before `setup` runs again.
