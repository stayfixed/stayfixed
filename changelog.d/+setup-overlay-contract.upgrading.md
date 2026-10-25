`stayfixed setup --overlay` changed what a script or a habit can rely on. `--yes` is gone from
`setup`: naming `create:<owner>/<name>` is the request, and a command line that still passes
`--yes` is refused by the parser. `setup --overlay` no longer refuses a place for the overlay,
another repository's work tree included: where it lives is yours to choose, and `stayfixed
doctor`'s `overlay-requires` row warns when another repository's work tree holds it. And
`stayfixed attach` no longer runs `pre-commit install` in the overlay: `setup --overlay` installs
the commit-time secret scan when it makes or records one, and `doctor`'s `pre-commit` row says
when it is missing.
