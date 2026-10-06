`stayfixed memory index` (with or without `--check`) and `stayfixed memory fit` now warn about a
missing trust record whenever the harness memory link to the store would wait for one. They used
to ask a narrower question, so an overlay-mode store with no committed `MEMORY.md` read as
trusted, with no warning and `"trusted": true` in `--json`, while its link was never made. The
warning now prints whenever a note, or the store's own directory, is inside the repository and no
`stayfixed memory trust --in-repo-memory` record matches it: in overlay mode, every store until
that record is made. For an overlay store whose notes all live in the overlay it says only that
the link waits, since the standing-rules and volatile-notes bundles still deliver those notes.
