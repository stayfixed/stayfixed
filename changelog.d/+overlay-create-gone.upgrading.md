`stayfixed overlay create`, `stayfixed overlay init` and `stayfixed overlay publish-template` are
gone; `stayfixed setup --overlay` is the one entry for an overlay. `--overlay <path>` naming an
existing overlay records it, as before, and now installs its commit-time secret scan too, which a
second machine recording its clone of the overlay had to do by hand; naming nothing, or an empty
directory you can list and write, it renders the shipped template there with no network call, makes it a git repository on
`main`, installs the commit-time secret scan and records it, where `overlay create --local` and
`overlay init` used to be run by hand. A mistyped path is therefore rendered at rather than refused,
and `setup` says so when the root it records replaces the one the machine configuration held. The
note that the commit-time secret scan is not installed names the overlay's path quoted, as the rest
of the report does.
`--overlay create:<owner>/<name>` generates the overlay on GitHub and installs the secret scan, as
before. The overlay template repository is
published with `uv run python scripts/publish_template.py --owner <account> [--yes]` from a
stayfixed checkout, a maintainer's script rather than a command stayfixed ships.
