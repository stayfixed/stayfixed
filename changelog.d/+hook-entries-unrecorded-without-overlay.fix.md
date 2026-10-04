`stayfixed doctor`'s `hook-entries` row is red for a hook entry that claims the stayfixed marker
and that nothing on this machine vouches for. A repository could commit a marked entry in
`.claude/settings.json` beside a `.stayfixed/local/attach.json` — one recording some other entry,
one recording that entry itself under any store it liked, or one that does not parse at all — and
the row warned and the report exited 0, on a machine that records no private overlay and, for a
ledger that does not parse, on every machine. What the overlay grants is now asked of the overlay
this machine records, never of the committed file, and that file, readable or not, no longer turns
the red into a warning. The row still warns while an overlay this machine records cannot be read,
or `git` cannot run. A ledger that cannot be read beside marked entries your overlay grants is a
warning, whose remedy is to remove the file and run `stayfixed attach` to write a new one. One
consequence: your own checkout opened on a new machine before `stayfixed setup --overlay` has run
reads red, because nothing there can vouch for the entries your last attach installed yet; run
`stayfixed setup --overlay <path>`, then `stayfixed attach`.
