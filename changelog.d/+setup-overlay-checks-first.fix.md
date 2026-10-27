`stayfixed setup --overlay create:<owner>/<name>` now looks at `<home>/<name>` before it asks
GitHub anything: a file there, or a directory holding something that is not an overlay, is refused
with nothing written and no repository created, where the clone used to meet it only after `gh repo
create` had made a private repository nothing then recorded; an empty directory you can list and
write is cloned into, a link there is refused in the same way, and the overlay an earlier run made
is left alone. A directory you cannot search, or one holding no overlay that you cannot both list
and write, is refused in one sentence, naming that directory. Once `gh repo create` has run, every
refusal says the repository may now exist on GitHub and how to record it: clone it to
`<home>/<name>`, then run `stayfixed setup --overlay <home>/<name>`. An `--overlay` path beginning
with `~` is refused while `HOME` is empty or relative, where it was read against `/` or the working
directory.
