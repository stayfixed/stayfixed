`stayfixed setup --overlay` now judges where an overlay may live against the repository `--root` is
in, and compares nothing with a `--root` git finds no repository for (no `.git` at or above it).
`stayfixed setup --overlay create:<owner>/<name> --yes` run in a home directory that is not a
repository is no longer refused for creating the overlay inside it; run in a home that is a git work
tree with its `.git` there, such as a dotfiles clone, it is still refused before anything is created
on GitHub. A home whose dotfiles repository keeps its git directory elsewhere, reached through
`--git-dir` and `--work-tree`, and one another version control system tracks, are not compared. An
overlay inside a checkout of any other repository, including a checkout of its own nested inside
one, is now refused wherever `--root` is.
