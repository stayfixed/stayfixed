`stayfixed setup --git-hooks` and `stayfixed setup --overlay` now print a path a repository can
spell in a refusal quoted, with every control character escaped: the hooks directory, which a
repository's `core.hooksPath` or a submodule's name chooses, a repository's git directory, and in
`setup --overlay`'s refusals the overlay, `--root` and the directory `git` was asked from, any of
which can be reached through a link a repository commits, as can the path `setup` could not ask
about before its first write. An escape sequence in such a name reached the terminal that read the
refusal. The lines `setup --git-hooks` prints when it installs or removes the hook quote the hook's
path the same way; `--json` carries it as it is.
