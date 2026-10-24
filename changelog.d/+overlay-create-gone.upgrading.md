`stayfixed overlay create`, `stayfixed overlay init` and `stayfixed overlay publish-template` are
gone; `stayfixed setup --overlay` is the one entry for an overlay. `--overlay <path>` naming an
existing overlay records it, as before; naming nothing, it renders the shipped template there with
no network call, makes it a git repository on `main`, installs the commit-time secret scan and
records it, where `overlay create --local` and `overlay init` used to be run by hand.
`--overlay create:<owner>/<name>` generates the overlay on GitHub, names its identity record after
`<owner>/<name>` and installs the secret scan, as before. The overlay template repository is
published with `uv run python scripts/publish_template.py --owner <account> [--yes]` from a
stayfixed checkout, a maintainer's script rather than a command stayfixed ships.
