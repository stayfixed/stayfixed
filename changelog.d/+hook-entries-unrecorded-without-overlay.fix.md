`stayfixed doctor`'s `hook-entries` row is red for a hook entry that claims the stayfixed marker and
that nothing on this machine vouches for. What the overlay grants is now asked of the overlay this
machine records, never of the committed files. A repository could commit a marked entry in
`.claude/settings.json` and keep the row at a warning, and the report at exit 0, in each of these
ways:

- beside a `.stayfixed/local/attach.json` recording some other entry, or recording that entry
  itself under any store it liked, on a machine that records no private overlay;
- beside a `.stayfixed/local/attach.json` that does not parse, on every machine;
- by giving `project.name` in `stayfixed.toml` a value no directory under the overlay's `projects/`
  can carry, on every machine: the name of a file kept there, which on a filesystem that ignores
  case includes `readme.md` beside the `README.md` every overlay ships, or a name longer than the
  filesystem allows;
- on Python 3.11 to 3.13, by committing the ledger, or another settings file, as a symbolic link to
  a name longer than the filesystem allows, which made the whole row a warning that it could not
  read something it needed;
- by putting one byte that is not UTF-8 anywhere in the settings file holding the entry, which made
  the row read the whole file as one it could not read.

Now neither the ledger, readable or not, nor such a name turns the red into a warning. A ledger
behind such a link reads as one that cannot be read, and a settings file behind one as a file the
row could not read. An overlay with no directory for the name grants that project only what it
grants every project. A byte that is not UTF-8 is read as a replacement character, so the entries
in the file are judged as they would be without it. The row still warns while an overlay this
machine records cannot be read, or `git` cannot run.

`stayfixed attach` and `stayfixed attach --check` refuse such a name, with exit 2, before writing
anything; they used to stop on the read that failed. A ledger that cannot be read beside marked
entries your overlay grants is a warning, whose remedy is to remove the file and run `stayfixed
attach` to write a new one. One consequence: your own checkout opened on a new machine before
`stayfixed setup --overlay` has run reads red, because nothing there can vouch for the entries your
last attach installed yet; run `stayfixed setup --overlay <path>`, then `stayfixed attach`.
