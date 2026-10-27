The recommended preset's commit types no longer include stayfixed's own `harden` and `guard`: they
are now the eleven `@commitlint/config-conventional` lists. A repository that kept the preset's
list rather than setting `[commit_messages] types` gets the new one, so `stayfixed assess`'s
`commit-types` advice now names a `harden:` or `guard:` commit subject there. To keep them, set
`types` under `[commit_messages]` in `stayfixed.toml`.
