`stayfixed setup --overlay` now judges where an overlay may live against the repository `--root` is
in, and compares nothing with a `--root` that is in no repository. `stayfixed setup --overlay
create:<owner>/<name> --yes` run in a home directory that is not a repository is no longer refused
for creating the overlay inside it; run in a home that is a repository, such as a dotfiles work
tree, it is still refused before anything is created on GitHub. An overlay inside a checkout of any
other repository, including a checkout of its own nested inside one, is now refused wherever
`--root` is.
