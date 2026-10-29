`stayfixed assess` and `stayfixed adopt promote` now give a link that differs from git's spelling
only in case the remedy that fits it when the difference is in a symlinked directory on the way:
a link to `Alias/notes.md`, where git tracks the symlink `alias` and the file it leads to, is a
`case-differs` item that says to spell the link as `git ls-files` does, where it used to be an
`untracked` item that said to commit a file already committed. A case difference is read as one
only when git's spelling reaches files git tracks all the way: a link to `Notes.md`, where git
tracks `notes.md` as a symlink to an ignored file, is now `untracked` and names that file, where it
used to say that respelling the link would do. A `case-differs` item names the path as the
document wrote it.
