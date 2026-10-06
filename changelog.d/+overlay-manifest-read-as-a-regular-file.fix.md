A named pipe, or anything else that is not a regular file, at your overlay's
`.claude-plugin/plugin.json` no longer hangs the session-start hook, `stayfixed doctor`'s
`overlay-requires` row or `stayfixed overlay upgrade`. Each now reads the overlay's manifests the
way `stayfixed setup` already did: a regular file only, followed through a link, up to 64 MiB.
Such a manifest declares no version floor and names no owner, and `setup` refuses the overlay as
before.
