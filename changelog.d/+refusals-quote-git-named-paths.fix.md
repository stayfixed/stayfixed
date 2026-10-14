`stayfixed setup --git-hooks` and `stayfixed setup --overlay` now print a path `git` names in a
refusal quoted, with every control character escaped: the hooks directory, which a repository's
`core.hooksPath` or a submodule's name chooses, and a repository's git directory. An escape sequence
in such a name reached the terminal that read the refusal.
