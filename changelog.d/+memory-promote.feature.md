A note now counts as yours only once you promote it. `stayfixed memory promote NOTE…` records the
digest of each named note's bytes in `trust.json` (kind `reviewed`), and `--changed` does so for
every note that is not reviewed. The digest alone decides, so the same bytes count as reviewed in
every worktree, after the store moves and under another name. Only a reviewed note flagged `startup` is a standing rule; a note
a repository commits, one an agent or the harness's writer wrote, and one edited since it was
promoted arrive in the volatile-notes bundle instead, labelled `[unreviewed]` and inside the
region that marks them as data, in every memory mode, and `stayfixed memory index` ends such a
note's line in `MEMORY.md` with the same label. A session hears one line, "N notes are
unreviewed", when that set has changed since the last session. `trust list` lists the reviewed
notes and `trust revoke reviewed --subject PATH` withdraws one; `memory inventory` reports each
note's `reviewed` status and an `unreviewed` total.
