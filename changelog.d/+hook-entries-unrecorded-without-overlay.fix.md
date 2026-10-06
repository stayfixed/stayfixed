`stayfixed doctor`'s `hook-entries` row is red for a hook entry that claims the stayfixed marker and
that nothing on this machine vouches for. A repository could commit a marked entry in
`.claude/settings.json` beside a `.stayfixed/local/attach.json` — one recording some other entry,
one recording that entry itself under any store it liked, or one that does not parse at all — and
the row warned and the report exited 0, on a machine that records no private overlay and, for a
ledger that does not parse, on every machine. It could do the same on every machine by giving
`project.name` in `stayfixed.toml` a value no directory under the overlay's `projects/` can carry:
the name of a file kept there, which on a filesystem that ignores case includes `readme.md` beside
the `README.md` every overlay ships, or a name longer than the filesystem allows. On Python 3.11 to
3.13 it could also commit the ledger, or another settings file, as a symbolic link to a name longer
than the filesystem allows, and the whole row became a warning that it could not read something it
needed. What the overlay grants is now asked of the overlay this machine records, never of the
committed files: neither the ledger, readable or not, nor such a name turns the red into a warning;
a ledger behind such a link reads as one that cannot be read and a settings file behind one as a
file the row could not read; and an overlay with no directory for the name grants that project only
what it grants every project. It could also put one byte that is not UTF-8 anywhere in the settings
file holding the entry: the row read the whole file as one it could not read, and warned. Such a
byte is now read as a replacement character, so the entries in the file are judged as they would be
without it. The row still warns while an overlay this machine records cannot
be read, or `git` cannot run. `stayfixed attach` and `stayfixed attach --check` refuse such a name,
with exit 2, before writing anything; they used to stop on the read that failed. A ledger that
cannot be read beside marked entries your overlay grants is a warning, whose remedy is to remove the
file and run `stayfixed attach` to write a new one. One consequence: your own checkout opened on a
new machine before `stayfixed setup --overlay` has run reads red, because nothing there can vouch
for the entries your last attach installed yet; run `stayfixed setup --overlay <path>`, then
`stayfixed attach`.
