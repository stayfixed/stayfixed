`stayfixed doctor`'s `hook-entries` row is red for a hook entry that claims the stayfixed marker
and that nothing on this machine vouches for. A repository could commit a marked entry in
`.claude/settings.json` beside a `.stayfixed/local/attach.json` — one recording some other entry,
or recording that entry itself under any store it liked — and on a machine that records no
private overlay the row warned and the report exited 0. What the overlay grants is now asked of
the overlay this machine records, never of the committed file, and an entry the ledger records
reads as a warning only while an overlay this machine records cannot be read. One consequence:
your own checkout opened on a new machine before `stayfixed setup --overlay` has run reads red,
because nothing there can vouch for the entries your last attach installed yet; run
`stayfixed setup --overlay <path>`, then `stayfixed attach`.
