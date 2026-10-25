`stayfixed setup --overlay create:<owner>/<name>` now looks at `<home>/<name>` before it asks
GitHub anything: a file there, or a directory holding something that is not an overlay, is refused
with nothing written and no repository created, where the clone used to meet it only after `gh repo
create` had made a private repository nothing then recorded; an empty directory is cloned into, and
the overlay an earlier run made is left alone. Once `gh repo create` has run, every refusal says
the repository may now exist on GitHub and how to record it: clone it to `<home>/<name>`, then run
`stayfixed setup --overlay <home>/<name>`.
Naming `create:` is the request, so `--yes` is gone from `setup`, and a command line that still
passes it is refused by the parser. `setup --overlay` no longer refuses a place for the overlay:
where it lives is yours to choose, and `stayfixed doctor`'s `overlay-requires` row warns when
another repository's work tree holds it. `stayfixed attach` no longer runs `pre-commit install` in
the overlay; `setup --overlay` installs the commit-time secret scan when it makes one, and
`doctor`'s `pre-commit` row says when it is missing. And `init`, `upgrade` and `uninstall` go on
when `git check-ignore` cannot answer, timing out under load or not installed, saying so in a
`note:` line and in `unanswered` under `--json`, where they used to refuse until it answered.
