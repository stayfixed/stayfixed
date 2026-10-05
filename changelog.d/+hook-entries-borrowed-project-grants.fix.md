`stayfixed doctor`'s `hook-entries` row no longer lets a repository borrow another project's hook
grants by naming itself after it. A clone could set `project.name` in `stayfixed.toml` to the name
of another project in your overlay, commit a marked hook entry equal to one that project's
`projects/<name>/claude/hooks.json` grants, and commit a `.stayfixed/local/attach.json` recording
it: the row read "all accounted for" and the report exited 0. What a project's own directory in the
overlay grants now counts only for a checkout that project's record binds, the one whose `origin`
is the remote recorded there; any other checkout is granted only what `common/` grants every
project, so the borrowed entry is red. Nothing under that project's directory can turn the red into
a warning either: its hook file is not read, and a `project.toml` there that cannot be read binds
nothing, where it used to make the overlay one that "could not be asked", a warning and an exit of
0. Your own bound checkouts are unaffected. Two consequences: if your own `project.toml` cannot be
read, `attached` says the overlay could not be asked and your per-project entries are red, rather
than a warning, until the record is repaired; and an overlay whose `projects/` is a file, rather
than a directory, now reads as holding no binding for the checkout, so `attached` warns about that
and `hook-entries` judges entries against `common/` alone, where it used to warn that the overlay
could not be asked.
