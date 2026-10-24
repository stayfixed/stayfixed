Notes committed to a repository — a `local-only` or `in-repo` store — reach a session with no
approval, as the harness delivers the same repository's `CLAUDE.md`, and only as data: the
`volatile-notes` bundle carries them inside the delimited region, and the `standing-rules` bundle
carries none of them, whatever `startup` rank a note claims. So `stayfixed trust approve` and
`stayfixed memory trust` are gone with nothing in their place, and `memory index` and `memory fit`
no longer speak of an approval or carry `trusted` in `--json`. A note holding the region's marker is
no longer refused: the region's nonce is drawn again until it is one the note does not hold. The
store approvals already in `~/.config/stayfixed/trust.json` are inert. `stayfixed trust list` now
lists every approval on the machine, so its `--all` is gone, and `stayfixed trust revoke KIND`
takes the subject it withdraws with `--subject`, which it now requires; `stayfixed trust revoke
memory --subject KEY` removes an old store approval.
