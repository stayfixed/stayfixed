`stayfixed memory trust --in-repo-memory` is gone with nothing in its place: notes committed to a
repository — a `local-only` or `in-repo` store — now reach a session with no approval, as the
harness delivers the same repository's `CLAUDE.md`, and only as data: the `volatile-notes` bundle
carries them inside the delimited region, and the `standing-rules` bundle carries none of them
until you promote one with `stayfixed memory promote`, whatever `startup` rank a note claims. A
script that ran `memory trust` must drop the call. `memory index` and `memory fit` no longer speak
of an approval or carry `trusted` in `--json`. A note holding the region's marker is no longer
refused: the region's nonce is drawn again until it is one the note does not hold. The store
approvals 0.3.1 recorded in `~/.config/stayfixed/trust.json` are no longer read: `stayfixed trust
list` shows none of them, and the first command that records an approval, such as `memory
promote`, replaces the file with the new versioned record and drops them. A 0.3.1 reading that
record finds no approval in it.
