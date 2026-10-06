`stayfixed attach` and `attach --check` now refuse, before anything is written, a
`.claude/settings.local.json` that stayfixed's own write-back would make longer than it reads,
64 MiB: "would be longer than this reader reads once written back". Written back indented, a short
document many levels deep grows by its depth on every line, so a 12 KB file 6,000 lists deep
became 72 MB, which `attach` wrote and then refused to read, as did every `detach` after it. Every
JSON document stayfixed writes back indented — a settings file `attach`, `detach`, `init`,
`upgrade` or `setup` rewrites, an overlay manifest `overlay init` renames — is refused the same way
before it is written, so no command leaves behind a file its next read refuses.
