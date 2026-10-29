`stayfixed assess` and `stayfixed adopt promote` now give a path whose spelling differs from git's
only in case the remedy that fits it wherever on the path the difference is, a symlinked directory
included: when the rest of the path is tracked, it is a `case-differs` item that says to spell it as
`git ls-files` does. A link to `Alias/notes.md`, where git tracks the symlink `alias` and the file it
leads to, used to be an `untracked` item that said to commit a file already committed. When git's
spelling leads on to a file git does not track, the item is `untracked` and names that file: a link
to `Notes.md`, where git tracks `notes.md` as a symlink to an ignored file, used to be told that
respelling the link would do. A `case-differs` item names the path as the document wrote it, where
it could name the path a symlink led to.
