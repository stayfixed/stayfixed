`stayfixed trust` is one command family for every approval on the machine. `stayfixed trust list`
shows each kind's state in this checkout — approved, lapsed or missing — and the exact command
that approves what is not; `--all` lists every approval recorded on the machine. `stayfixed trust
approve memory` approves the notes committed to this repository, and prints the kind, subject and
digest it recorded. `stayfixed trust revoke memory` withdraws the
approval from anywhere, and exits 1 listing what is recorded when nothing matches; where the
checkout cannot be described, as once `stayfixed.toml` is gone, it says so and names
`--subject` with a key `stayfixed trust list --all --json` prints. `list` and `revoke` read the
checkout as a session does, so a `stayfixed.toml` a newer stayfixed added to still shows the
approval a session uses, and revoking it works. Every message
that told you to run `stayfixed memory trust --in-repo-memory` now names `stayfixed trust approve
memory`, and asks for the person at the machine to run it, telling an agent that reads it not to.
`stayfixed doctor`'s `attached` row sends a trust record it cannot read to `stayfixed trust list
--all`, which says why.
